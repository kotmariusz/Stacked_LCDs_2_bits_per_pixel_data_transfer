/* USER CODE BEGIN Header */
/**
  ******************************************************************************
  * @file           : main.c
  * @brief          : Show the frames from frames.h, made by the Colab notebook
  ******************************************************************************
  * @attention
  *
  * Copyright (c) 2026 STMicroelectronics.
  * All rights reserved.
  *
  * This software is licensed under terms that can be found in the LICENSE file
  * in the root directory of this software component.
  * If no LICENSE file comes with this software, it is provided AS-IS.
  *
  * The code inside the USER CODE sections and the description below:
  * Copyright (c) 2026 Mariusz Kot, MIT License (LICENSE in the repository root).
  *
  ******************************************************************************
  *
  * The Send text cell in colab/lcd_codec_colab.ipynb turns a message into
  * finished frames - header, CRC, markers and all - and writes them to
  * frames.h. This main does nothing but put those bytes on the two panels, so
  * what is shown is exactly what the notebook made.
  *
  * TO USE
  *   1. In Colab, run Setup, then 1 Send text with your MESSAGE, CELL_PX and
  *      USE_MARKERS. It downloads encoded.zip; frames.h is inside.
  *   2. Put frames.h in Core/Inc/ and this file over Core/Src/main.c.
  *   3. Flash. (With a frames.h from an older notebook, first set FRAME_LIST,
  *      CELL_PX and USE_MARKERS below - see WHAT TO SHOW.)
  *
  * A message that fits in one frame gives one array in frames.h, called
  * `frame`, and it stays on the panels. A longer one gives frame_1, frame_2,
  * ... - list them all and each is shown for DWELL_MS in turn, so you can
  * photograph them one by one. The Decode cell reads the photographs.
  *
  * CELL TO PANEL MAPPING (as everywhere else in this project)
  *   cell value bit 0 -> panel 1        cell value bit 1 -> panel 2
  *   so   0 = both off      1 = panel 1 only
  *        2 = panel 2 only  3 = both on
  *
  * Wiring (unchanged):
  *   shared : SCK=PA5   SDI/MOSI=PA7   DC=PA4
  *   LCD1   : CS=PA3    RST=PA2
  *   LCD2   : CS=PA1    RST=PA0
  *
  ******************************************************************************
  */
/* USER CODE END Header */
/* Includes ------------------------------------------------------------------*/
#include "main.h"
#include "spi.h"
#include "gpio.h"

/* USER CODE BEGIN Includes */
#include "st7567.h"
#include "frames.h"          /* from the Colab Send text cell, in Core/Inc/ */
/* USER CODE END Includes */

/* USER CODE BEGIN PD */

/* ====== WHAT TO SHOW ======
 * A frames.h from the current notebook says all three of these itself, and
 * what it says is used. Only for an older frames.h without them do the values
 * here count - set them to match the Colab cell that made it:
 *
 *   FRAME_LIST    the arrays in frames.h, in order. One frame: frame
 *                 a longer message: frame_1, frame_2, frame_3 (and so on)
 *   CELL_PX       as in the cell; its first comment line in frames.h says too
 *   USE_MARKERS   the cell's tick box, on by default. Keep it on: the Decode
 *                 cell expects the markers and cannot read a frame without
 *                 them.
 *
 * A mismatch is caught when compiling, not left to show up as an unreadable
 * frame. */
#ifndef FRAME_LIST
#define FRAME_LIST   frame
#endif

#ifdef FRAMES_CELL_PX
#define CELL_PX      FRAMES_CELL_PX
#else
#define CELL_PX      8
#endif

#ifdef FRAMES_USE_MARKERS
#define USE_MARKERS  FRAMES_USE_MARKERS
#else
#define USE_MARKERS  1
#endif

/* How long each frame stays up when there are several. One frame stays up
 * for good. Give yourself time to take the photograph. */
#define DWELL_MS     4000

#define CODE_W       (ST7567_WIDTH  / CELL_PX)
#define CODE_H       (ST7567_HEIGHT / CELL_PX)

#if USE_MARKERS
#define MARKER_COUNT 4
#else
#define MARKER_COUNT 0
#endif

/* Cells left for payload, and therefore how many whole bytes a frame holds -
 * the same sum the notebook does, so it is also the size of every array in
 * frames.h. */
#define PAYLOAD_CELLS  ((CODE_W * CODE_H) - MARKER_COUNT)
#define PAYLOAD_BYTES  (PAYLOAD_CELLS / 4)

#define FIRST_(a, ...)  a
#define FIRST(...)      FIRST_(__VA_ARGS__, 0)
_Static_assert(sizeof(FIRST(FRAME_LIST)) == PAYLOAD_BYTES,
               "frames.h was made with a different CELL_PX or USE_MARKERS "
               "than this file says - set them to match the Colab cell");

#define LCD_DC_PORT     GPIOA
#define LCD_DC_PIN      GPIO_PIN_4

#define LCD1_CS_PORT    GPIOA
#define LCD1_CS_PIN     GPIO_PIN_3
#define LCD1_RST_PORT   GPIOA
#define LCD1_RST_PIN    GPIO_PIN_2

#define LCD2_CS_PORT    GPIOA
#define LCD2_CS_PIN     GPIO_PIN_1
#define LCD2_RST_PORT   GPIOA
#define LCD2_RST_PIN    GPIO_PIN_0

#define LCD_CONTRAST    100

/* Column offset per panel. Panel 2 runs with the segment direction reversed
 * (ADC 0xA1) so its visible window starts 4 columns further along. Correcting
 * it here moves the ADDRESS, so nothing is clipped. If panel 2 is still out,
 * try 0 or 8. */
#define PANEL1_COL_OFFSET   0
#define PANEL2_COL_OFFSET   4

/* Rewrite the frame every REFRESH_MS, so a byte damaged on the SPI wire is
 * repaired within a fraction of a second instead of sitting there until the
 * next reset, and re-initialise every REINIT_MS in case a COMMAND byte was
 * hit. Neither changes anything on screen when all is well. */
#define REFRESH_MS      400
#define REINIT_MS       10000

/* SPI clock, set at boot so CubeMX does not have to be regenerated. On a
 * 72 MHz APB2, _64 = 1.1 MHz: slow, but two panels on breadboard jumpers are a
 * lot of capacitance, and a static frame has all the time in the world. */
#define SPI_PRESCALER   SPI_BAUDRATEPRESCALER_64

/* USER CODE END PD */

/* USER CODE BEGIN PV */
static ST7567_t lcd1;
static ST7567_t lcd2;

static const uint8_t *const g_frames[] = { FRAME_LIST };
#define FRAME_COUNT  (sizeof(g_frames) / sizeof(g_frames[0]))
/* USER CODE END PV */

void SystemClock_Config(void);
/* USER CODE BEGIN PFP */
static void panels_bring_up(void);
static void draw_frame(const uint8_t *frame);
/* USER CODE END PFP */

/* USER CODE BEGIN 0 */

/* Change only the clock divider, in place. Not HAL_SPI_DeInit() and Init():
 * DeInit switches the SPI clock off and hands PA5 and PA7 back as plain GPIO,
 * and those two pins are shared with both panels. */
static void spi_set_speed(uint32_t prescaler)
{
  __HAL_SPI_DISABLE(&hspi1);
  MODIFY_REG(hspi1.Instance->CR1, SPI_CR1_BR, prescaler);
  hspi1.Init.BaudRatePrescaler = prescaler;
  __HAL_SPI_ENABLE(&hspi1);
}

#if USE_MARKERS
/* Is this cell reserved for a marker, and if so which state does it carry?
 * Same layout as the notebook: three corners, plus the cell diagonally inside
 * the bottom-left one. */
static int marker_state(uint16_t row, uint16_t col)
{
  if (row == 0 && col == 0)             return 0;
  if (row == 0 && col == CODE_W - 1)    return 1;
  if (row == CODE_H - 1 && col == 0)    return 2;
  if (row == CODE_H - 2 && col == 1)    return 3;
  return -1;
}
#endif

/* Paint one cell as a solid CELL_PX square on whichever panels its bits ask
 * for. Both panels are drawn at the same scale and the grid runs flush to the
 * glass. */
static void fill_cell(ST7567_t *d, uint16_t cx, uint16_t cy)
{
  ST7567_FillRect(d, (uint8_t)(cx * CELL_PX), (uint8_t)(cy * CELL_PX),
                  CELL_PX, CELL_PX, 1);
}

static void draw_cell(uint16_t index, uint8_t value)
{
  uint16_t cx = index % CODE_W;
  uint16_t cy = index / CODE_W;

  if (value & 0x01) fill_cell(&lcd1, cx, cy);
  if (value & 0x02) fill_cell(&lcd2, cx, cy);
}

/* Bring both panels up in a way that survives a warm reset: chip selects
 * high before anything else so neither panel listens while pins float, both
 * held in reset together, a pause for the supplies, and the init run twice so
 * the second pass lands on quiet, powered panels. */
static void panels_bring_up(void)
{
  HAL_GPIO_WritePin(LCD1_CS_PORT, LCD1_CS_PIN, GPIO_PIN_SET);
  HAL_GPIO_WritePin(LCD2_CS_PORT, LCD2_CS_PIN, GPIO_PIN_SET);
  HAL_GPIO_WritePin(LCD_DC_PORT,  LCD_DC_PIN,  GPIO_PIN_SET);

  HAL_GPIO_WritePin(LCD1_RST_PORT, LCD1_RST_PIN, GPIO_PIN_RESET);
  HAL_GPIO_WritePin(LCD2_RST_PORT, LCD2_RST_PIN, GPIO_PIN_RESET);
  HAL_Delay(50);
  HAL_GPIO_WritePin(LCD1_RST_PORT, LCD1_RST_PIN, GPIO_PIN_SET);
  HAL_GPIO_WritePin(LCD2_RST_PORT, LCD2_RST_PIN, GPIO_PIN_SET);
  HAL_Delay(150);

  for (int pass = 0; pass < 2; pass++) {
    ST7567_Init(&lcd1);
    HAL_Delay(20);
    ST7567_Init(&lcd2);
    HAL_Delay(20);
  }
}

/* Walk the grid in reading order, row by row from the top left. Marker cells
 * get their fixed state; every other cell takes the next two bits of the
 * frame, most significant first - exactly the notebook's frame_to_cells. */
static void draw_frame(const uint8_t *frame)
{
  ST7567_Clear(&lcd1);
  ST7567_Clear(&lcd2);

  uint16_t bit = 0;

  for (uint16_t row = 0; row < CODE_H; row++) {
    for (uint16_t col = 0; col < CODE_W; col++) {
      uint16_t index = (uint16_t)(row * CODE_W + col);

#if USE_MARKERS
      int mk = marker_state(row, col);
      if (mk >= 0) {
        draw_cell(index, (uint8_t)mk);
        continue;
      }
#endif
      uint16_t byte_i = (uint16_t)(bit >> 3);
      uint8_t  shift  = (uint8_t)(6 - (bit & 7));
      uint8_t  value  = (byte_i < PAYLOAD_BYTES)
                        ? (uint8_t)((frame[byte_i] >> shift) & 0x03) : 0;
      draw_cell(index, value);
      bit = (uint16_t)(bit + 2);
    }
  }

  ST7567_Update(&lcd1);
  ST7567_Update(&lcd2);
}

/* USER CODE END 0 */

int main(void)
{
  HAL_Init();
  SystemClock_Config();
  MX_GPIO_Init();
  MX_SPI1_Init();

  /* USER CODE BEGIN 2 */

  lcd1.hspi     = &hspi1;
  lcd1.cs_port  = LCD1_CS_PORT;   lcd1.cs_pin  = LCD1_CS_PIN;
  lcd1.dc_port  = LCD_DC_PORT;    lcd1.dc_pin  = LCD_DC_PIN;
  lcd1.rst_port = LCD1_RST_PORT;  lcd1.rst_pin = LCD1_RST_PIN;
  lcd1.contrast   = LCD_CONTRAST;
  lcd1.col_offset = PANEL1_COL_OFFSET;
  lcd1.adc_cmd  = 0xA0;
  lcd1.com_cmd  = 0xC0;

  lcd2.hspi     = &hspi1;
  lcd2.cs_port  = LCD2_CS_PORT;   lcd2.cs_pin  = LCD2_CS_PIN;
  lcd2.dc_port  = LCD_DC_PORT;    lcd2.dc_pin  = LCD_DC_PIN;
  lcd2.rst_port = LCD2_RST_PORT;  lcd2.rst_pin = LCD2_RST_PIN;
  lcd2.contrast   = LCD_CONTRAST;
  lcd2.col_offset = PANEL2_COL_OFFSET;
  lcd2.adc_cmd  = 0xA1;
  lcd2.com_cmd  = 0xC0;

  spi_set_speed(SPI_PRESCALER);
  panels_bring_up();

  /* USER CODE END 2 */

  /* USER CODE BEGIN WHILE */
  uint32_t last_reinit = HAL_GetTick();
  uint32_t shown_since = HAL_GetTick();
  uint32_t current = 0;

  while (1)
  {
    /* Rewrite the current frame over and over: identical bytes, so nothing
     * moves on screen unless the previous write was damaged - in which case
     * this is what repairs it. */
    draw_frame(g_frames[current]);
    HAL_Delay(REFRESH_MS);

    if (FRAME_COUNT > 1 &&
        (uint32_t)(HAL_GetTick() - shown_since) >= DWELL_MS) {
      current = (current + 1) % FRAME_COUNT;
      shown_since = HAL_GetTick();
    }

    if ((uint32_t)(HAL_GetTick() - last_reinit) >= REINIT_MS) {
      panels_bring_up();
      last_reinit = HAL_GetTick();
    }
    /* USER CODE END WHILE */

    /* USER CODE BEGIN 3 */
  }
  /* USER CODE END 3 */
}

/**
  * @brief System Clock Configuration
  * @retval None
  */
void SystemClock_Config(void)
{
  RCC_OscInitTypeDef RCC_OscInitStruct = {0};
  RCC_ClkInitTypeDef RCC_ClkInitStruct = {0};

  RCC_OscInitStruct.OscillatorType = RCC_OSCILLATORTYPE_HSE;
  RCC_OscInitStruct.HSEState = RCC_HSE_ON;
  RCC_OscInitStruct.HSEPredivValue = RCC_HSE_PREDIV_DIV1;
  RCC_OscInitStruct.HSIState = RCC_HSI_ON;
  RCC_OscInitStruct.PLL.PLLState = RCC_PLL_ON;
  RCC_OscInitStruct.PLL.PLLSource = RCC_PLLSOURCE_HSE;
  RCC_OscInitStruct.PLL.PLLMUL = RCC_PLL_MUL9;
  if (HAL_RCC_OscConfig(&RCC_OscInitStruct) != HAL_OK)
  {
    Error_Handler();
  }

  RCC_ClkInitStruct.ClockType = RCC_CLOCKTYPE_HCLK|RCC_CLOCKTYPE_SYSCLK
                              |RCC_CLOCKTYPE_PCLK1|RCC_CLOCKTYPE_PCLK2;
  RCC_ClkInitStruct.SYSCLKSource = RCC_SYSCLKSOURCE_PLLCLK;
  RCC_ClkInitStruct.AHBCLKDivider = RCC_SYSCLK_DIV1;
  RCC_ClkInitStruct.APB1CLKDivider = RCC_HCLK_DIV2;
  RCC_ClkInitStruct.APB2CLKDivider = RCC_HCLK_DIV1;

  if (HAL_RCC_ClockConfig(&RCC_ClkInitStruct, FLASH_LATENCY_2) != HAL_OK)
  {
    Error_Handler();
  }
}

void Error_Handler(void)
{
  __disable_irq();
  while (1)
  {
  }
}
#ifdef USE_FULL_ASSERT
void assert_failed(uint8_t *file, uint32_t line)
{
}
#endif /* USE_FULL_ASSERT */
