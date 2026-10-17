/*
 * st7567.h - Minimal ST7567 128x64 monochrome LCD driver for STM32 HAL
 *
 * Hardware SPI (transmit only) + 3 GPIOs per display (CS, DC, RST).
 * Several displays can share the SPI bus, SCK, SDI and DC; each needs
 * its own CS and RST.
 *
 * Tested layout (Blue Pill STM32F103C8T6):
 *   shared : SCK=PA5  SDI=PA7  DC=PA4
 *   LCD1   : CS=PA3   RST=PA2
 *   LCD2   : CS=PA1   RST=PA0
 */

#ifndef ST7567_DRIVER_H
#define ST7567_DRIVER_H

#include "main.h"     /* pulls in the HAL headers CubeMX generated */
#include <stdint.h>

#define ST7567_WIDTH    128
#define ST7567_HEIGHT   64
#define ST7567_PAGES    (ST7567_HEIGHT / 8)
#define ST7567_BUFSIZE  (ST7567_WIDTH * ST7567_PAGES)

/* Some modules start at a non-zero column. If the image looks shifted
 * sideways by a few pixels, try 4 here instead of 0. */
#define ST7567_COL_OFFSET 0

/* Orientation. These map to the chip's segment/common direction commands,
 * so the framebuffer stays in normal top-left origin either way.
 *   ADC  0xA0 = normal      0xA1 = reversed  (horizontal)
 *   COM  0xC0 = normal      0xC8 = reversed  (vertical)
 * The four useful combinations: */
#define ST7567_ROT_0        0xA1, 0xC0   /* normal            */
#define ST7567_ROT_180      0xA0, 0xC8   /* rotated 180 deg   */
#define ST7567_MIRROR_X     0xA0, 0xC0   /* mirrored L-R      */
#define ST7567_MIRROR_Y     0xA1, 0xC8   /* mirrored top-bot  */

typedef struct {
    SPI_HandleTypeDef *hspi;

    GPIO_TypeDef *cs_port;   uint16_t cs_pin;
    GPIO_TypeDef *dc_port;   uint16_t dc_pin;
    GPIO_TypeDef *rst_port;  uint16_t rst_pin;

    uint8_t adc_cmd;         /* 0xA0 / 0xA1 */
    uint8_t com_cmd;         /* 0xC0 / 0xC8 */
    /* Column offset. The controller has 132 column drivers but the glass
     * shows only 128, so the visible window moves depending on the segment
     * direction: 0 with ADC normal (0xA0), usually 4 with ADC reversed
     * (0xA1). Shifting the ADDRESS rather than the drawing means nothing is
     * clipped at the edges. */
    uint8_t col_offset;

    uint8_t contrast;        /* EV register: 0..63 only. 38 is a good start. */

    uint8_t buf[ST7567_BUFSIZE];
} ST7567_t;

void ST7567_Init(ST7567_t *d);
void ST7567_SetContrast(ST7567_t *d, uint8_t value);
void ST7567_Clear(ST7567_t *d);
void ST7567_Fill(ST7567_t *d);
void ST7567_DrawPixel(ST7567_t *d, uint8_t x, uint8_t y, uint8_t on);
void ST7567_FillRect(ST7567_t *d, uint8_t x, uint8_t y,
                     uint8_t w, uint8_t h, uint8_t on);
void ST7567_Update(ST7567_t *d);

#endif /* ST7567_DRIVER_H */
