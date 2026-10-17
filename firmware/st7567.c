/*
 * st7567.c - Minimal ST7567 128x64 monochrome LCD driver for STM32 HAL
 */

#include "st7567.h"
#include <string.h>

/* ── low level ────────────────────────────────────────────────────────────── */

static void cs_low(ST7567_t *d)
{
    HAL_GPIO_WritePin(d->cs_port, d->cs_pin, GPIO_PIN_RESET);
}

static void cs_high(ST7567_t *d)
{
    HAL_GPIO_WritePin(d->cs_port, d->cs_pin, GPIO_PIN_SET);
}

/* Wait for the shift register to empty before releasing chip select.
 *
 * HAL_SPI_Transmit reports done once the last byte has been handed to the data
 * register, which is not the same as the last bit having left the pin. Raising
 * CS in between truncates that byte, and the panel is then one or more bits out
 * of step for everything that follows. Current HAL does wait on BSY for a
 * master transmit, so on most versions this changes nothing - it costs a few
 * cycles and removes the question. Bounded, so a flag that never clears cannot
 * wedge the display. */
static void spi_flush(ST7567_t *d)
{
    for (uint32_t guard = 0; guard < 200000u; guard++) {
        if (__HAL_SPI_GET_FLAG(d->hspi, SPI_FLAG_TXE) &&
            !__HAL_SPI_GET_FLAG(d->hspi, SPI_FLAG_BSY)) {
            return;
        }
    }
}

static void write_cmd(ST7567_t *d, uint8_t cmd)
{
    HAL_GPIO_WritePin(d->dc_port, d->dc_pin, GPIO_PIN_RESET);  /* DC low = command */
    cs_low(d);
    HAL_SPI_Transmit(d->hspi, &cmd, 1, HAL_MAX_DELAY);
    spi_flush(d);
    cs_high(d);
}

static void write_data(ST7567_t *d, uint8_t *data, uint16_t len)
{
    HAL_GPIO_WritePin(d->dc_port, d->dc_pin, GPIO_PIN_SET);    /* DC high = data */
    cs_low(d);
    HAL_SPI_Transmit(d->hspi, data, len, HAL_MAX_DELAY);
    spi_flush(d);
    cs_high(d);
}

/* ── init ─────────────────────────────────────────────────────────────────── */

void ST7567_Init(ST7567_t *d)
{
    /* Deassert chip select FIRST.
     *
     * On a warm reset the panels keep their power and their internal state,
     * while the MCU's pins spend a few microseconds as floating inputs
     * between the reset and MX_GPIO_Init(). Anything the panel picks up in
     * that window leaves it mid-command, which is what produces garbage on
     * screen that clears itself after a few resets. Taking CS high before
     * touching anything else stops the panel listening while we sort it out.
     */
    cs_high(d);
    HAL_GPIO_WritePin(d->dc_port, d->dc_pin, GPIO_PIN_SET);
    HAL_Delay(20);          /* let the rails and the panel settle */

    /* Hardware reset, generously timed. The datasheet minimum is short, but
     * a warm reset needs the panel driven low long enough to be certain the
     * internal state machine has actually let go. */
    HAL_GPIO_WritePin(d->rst_port, d->rst_pin, GPIO_PIN_SET);
    HAL_Delay(10);
    HAL_GPIO_WritePin(d->rst_port, d->rst_pin, GPIO_PIN_RESET);
    HAL_Delay(50);
    HAL_GPIO_WritePin(d->rst_port, d->rst_pin, GPIO_PIN_SET);
    HAL_Delay(120);

    write_cmd(d, 0xAE);                 /* display off while we reconfigure  */
    write_cmd(d, 0xE2);                 /* soft reset                        */
    HAL_Delay(20);

    write_cmd(d, 0xA2);                 /* LCD bias 1/9                      */
    write_cmd(d, d->adc_cmd);           /* segment direction 0xA0 / 0xA1     */
    write_cmd(d, d->com_cmd);           /* common direction  0xC0 / 0xC8     */
    write_cmd(d, 0x20 | 0x04);          /* regulation ratio 5.0              */

    write_cmd(d, 0x81);                 /* set EV (contrast) ...             */
    write_cmd(d, (uint8_t)(d->contrast & 0x3F));   /* ... 6-bit value        */

    /* Power up in stages, as the datasheet asks: booster first, then the
     * regulator, then the voltage follower. Switching all three on at once
     * works on some panels and not others. */
    write_cmd(d, 0x28 | 0x04);          /* booster on                        */
    HAL_Delay(5);
    write_cmd(d, 0x28 | 0x06);          /* + regulator on                    */
    HAL_Delay(5);
    write_cmd(d, 0x28 | 0x07);          /* + follower on                     */
    HAL_Delay(5);

    /* Clear the RAM before switching the panel on, so no garbage shows. */
    ST7567_Clear(d);
    ST7567_Update(d);

    write_cmd(d, 0xA4);                 /* show RAM contents, not all-on     */
    write_cmd(d, 0xA6);                 /* normal, not inverted              */
    write_cmd(d, 0xAF);                 /* display on                        */
}

void ST7567_SetContrast(ST7567_t *d, uint8_t value)
{
    /* The EV register is 6 bits wide. Anything above 63 wraps, so a value
     * like 200 would silently become 200 & 0x3F = 8. Clamp instead. */
    if (value > 63) {
        value = 63;
    }
    d->contrast = value;
    write_cmd(d, 0x81);
    write_cmd(d, (uint8_t)(value & 0x3F));
}

/* ── framebuffer ──────────────────────────────────────────────────────────── */

void ST7567_Clear(ST7567_t *d)
{
    memset(d->buf, 0x00, ST7567_BUFSIZE);
}

void ST7567_Fill(ST7567_t *d)
{
    memset(d->buf, 0xFF, ST7567_BUFSIZE);
}

/* Buffer layout: one byte spans 8 vertical pixels.
 * byte index = page * 128 + x, where page = y / 8, bit = y % 8. */
void ST7567_DrawPixel(ST7567_t *d, uint8_t x, uint8_t y, uint8_t on)
{
    if (x >= ST7567_WIDTH || y >= ST7567_HEIGHT) {
        return;
    }
    uint16_t idx = (uint16_t)(y >> 3) * ST7567_WIDTH + x;
    uint8_t  bit = 1u << (y & 7u);

    if (on) {
        d->buf[idx] |= bit;
    } else {
        d->buf[idx] &= (uint8_t)~bit;
    }
}

void ST7567_FillRect(ST7567_t *d, uint8_t x, uint8_t y,
                     uint8_t w, uint8_t h, uint8_t on)
{
    for (uint8_t j = 0; j < h; j++) {
        for (uint8_t i = 0; i < w; i++) {
            ST7567_DrawPixel(d, (uint8_t)(x + i), (uint8_t)(y + j), on);
        }
    }
}

/* ── push framebuffer to the panel ────────────────────────────────────────── */

void ST7567_Update(ST7567_t *d)
{
    write_cmd(d, 0x40);   /* start line = 0 */

    for (uint8_t page = 0; page < ST7567_PAGES; page++) {
        write_cmd(d, (uint8_t)(0xB0 | page));                       /* page addr  */
        write_cmd(d, (uint8_t)(0x10 | ((d->col_offset >> 4) & 0x0F)));  /* col hi */
        write_cmd(d, (uint8_t)(0x00 | (d->col_offset & 0x0F)));         /* col lo */
        write_data(d, &d->buf[(uint16_t)page * ST7567_WIDTH], ST7567_WIDTH);
    }
}
