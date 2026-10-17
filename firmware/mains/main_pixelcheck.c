/* USER CODE BEGIN Header */
/**
  ******************************************************************************
  * @file           : main.c
  * @brief          : Find out WHY pixels go missing or land a pixel out
  ******************************************************************************
  *
  * Missing or shifted pixels have several possible causes and they need
  * different fixes, so guessing is expensive. This firmware separates them.
  *
  * It draws a pattern in which a single lost bit is unmistakable, REDRAWS IT
  * CONTINUOUSLY, and optionally steps the SPI clock down through six speeds.
  * What you see tells you which fault you have:
  *
  *   WHAT YOU SEE                              CAUSE                  FIX
  *   ------------------------------------------------------------------------
  *   Pattern shimmers, flickers or the seam    bits lost on the        slow the
  *   jumps around while it is being redrawn    wire                    SPI clock,
  *                                                                    shorten
  *                                                                    wires
  *
  *   Pattern is rock steady but wrong - a      addressing or the       geometry,
  *   seam in one fixed place, or the outer     drawing geometry        not the
  *   column missing every time                                        bus
  *
  *   Clean at 1 MHz, breaks at 4.5 or 9 MHz    clock too fast for      prescaler
  *                                            the wiring              64 or 128
  *
  *   Breaks the same at every speed            not the bus at all      see below
  *
  *   A whole column or row never lights, at    dead segment, or a      reseat the
  *   any speed, in every pattern               bad flex connection     connector
  *
  *   All patterns faint, or pixels fade as     LCD bias / contrast,    try bias
  *   more of the screen lights up              or supply sag           0xA3, feed
  *                                                                    3V3 from a
  *                                                                    real supply
  *
  * HOW TO USE IT
  *   1. Flash as-is. PAT_VSTRIPES at a continuous redraw is the most
  *      revealing: single-column stripes, so one lost bit shifts the stripe
  *      phase and you get an obvious seam.
  *   2. Watch one full sweep. The tick marks along the very top row count the
  *      speed step: 1 tick = 9 MHz, 2 = 4.5, 3 = 2.25, 4 = 1.1, 5 = 0.56,
  *      6 = 0.28 MHz.
  *   3. Note the slowest step that still misbehaves, then read the table.
  *   4. Set PATTERN to PAT_RULER to check the geometry: it draws a 1-pixel
  *      border and a tick every 8 pixels, so you can see directly whether the
  *      outermost column and row are on the glass and where the cell edges
  *      fall on each panel.
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
#include <string.h>
/* USER CODE END Includes */

/* USER CODE BEGIN PD */

#define PAT_VSTRIPES  1   /* alternating single columns - shows a lost BYTE   */
#define PAT_HSTRIPES  2   /* alternating single rows    - shows a lost BIT    */
#define PAT_RULER     3   /* border + ticks every 8 px  - shows the geometry  */
#define PAT_ALLON     4   /* everything on - dead segments, supply sag        */
#define PAT_GRID8     5   /* the real 8 px cell checkerboard                  */
#define PAT_CORNERS   6   /* one pixel in each corner - shows clipping        */

#define PATTERN       PAT_VSTRIPES

/* Step the SPI clock down through six speeds, one per phase. Set to 0 to stay
 * at whatever CubeMX configured. */
#define SPEED_SWEEP   1

/* Redraw the pattern over and over inside each phase. This is the important
 * part: a fault in transmission moves about between redraws, a fault in
 * addressing or geometry does not. */
#define REDRAW_MS     120
#define DWELL_MS      4000

#define PANEL_BOTH    0
#define PANEL_ONE     1
#define PANEL_TWO     2
/* Driving one panel at a time halves the load on the bus and the current draw.
 * If one panel alone is clean and two together are not, the problem is loading
 * or supply, not the code. */
#define PANELS        PANEL_BOTH

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

#define PANEL1_COL_OFFSET   0
#define PANEL2_COL_OFFSET   4

/* USER CODE END PD */

/* USER CODE BEGIN PV */
static ST7567_t lcd1;
static ST7567_t lcd2;

static const uint32_t SPEEDS[] = {
  SPI_BAUDRATEPRESCALER_8,     /* 9     MHz on a 72 MHz APB2 */
  SPI_BAUDRATEPRESCALER_16,    /* 4.5   MHz  <- the setup guide's value */
  SPI_BAUDRATEPRESCALER_32,    /* 2.25  MHz */
  SPI_BAUDRATEPRESCALER_64,    /* 1.125 MHz */
  SPI_BAUDRATEPRESCALER_128,   /* 0.56  MHz */
  SPI_BAUDRATEPRESCALER_256    /* 0.28  MHz */
};
#define SPEED_COUNT (sizeof(SPEEDS)/sizeof(SPEEDS[0]))
/* USER CODE END PV */

void SystemClock_Config(void);
/* USER CODE BEGIN PFP */
static void panels_bring_up(void);
static void draw_pattern(uint8_t speed_step);
/* USER CODE END PFP */

/* USER CODE BEGIN 0 */

/* Change only the clock divider, in place.
 *
 * Deliberately NOT HAL_SPI_DeInit() + HAL_SPI_Init(): DeInit calls
 * HAL_SPI_MspDeInit(), which switches the SPI clock off and hands PA5 and PA7
 * back as plain GPIO. Those two pins are shared with both panels, so that
 * route can disturb the very thing being measured. Writing the BR field
 * directly cannot.
 *
 * The SPI_BAUDRATEPRESCALER_* constants are already positioned for the BR
 * field of CR1, so they drop straight in. */
static void spi_set_speed(uint32_t prescaler)
{
  __HAL_SPI_DISABLE(&hspi1);
  MODIFY_REG(hspi1.Instance->CR1, SPI_CR1_BR, prescaler);
  hspi1.Init.BaudRatePrescaler = prescaler;
  __HAL_SPI_ENABLE(&hspi1);
}

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

/* Paint the pattern into one framebuffer. Nothing here touches the bus, so a
 * difference between what this builds and what appears on the glass is a
 * transmission fault and nothing else. */
static void build_pattern(ST7567_t *d, uint8_t speed_step)
{
  ST7567_Clear(d);

#if PATTERN == PAT_VSTRIPES
  /* Every other column fully on. One lost byte shifts the phase of every
   * stripe after it, which reads as a seam straight down the screen. */
  for (uint16_t x = 0; x < ST7567_WIDTH; x += 2) {
    for (uint16_t y = 0; y < ST7567_HEIGHT; y++) {
      ST7567_DrawPixel(d, (uint8_t)x, (uint8_t)y, 1);
    }
  }

#elif PATTERN == PAT_HSTRIPES
  /* Every other row on - each byte becomes 0x55. One lost BIT shifts the rows
   * within the affected columns, so the stripes step up or down. */
  for (uint16_t y = 0; y < ST7567_HEIGHT; y += 2) {
    for (uint16_t x = 0; x < ST7567_WIDTH; x++) {
      ST7567_DrawPixel(d, (uint8_t)x, (uint8_t)y, 1);
    }
  }

#elif PATTERN == PAT_RULER
  /* A one-pixel border, plus a tick every 8 pixels inside it. If the border is
   * not visible all the way round, the outermost row or column is off the
   * glass - a column-offset or drawing-geometry problem, not a bus problem. */
  for (uint16_t x = 0; x < ST7567_WIDTH; x++) {
    ST7567_DrawPixel(d, (uint8_t)x, 0, 1);
    ST7567_DrawPixel(d, (uint8_t)x, ST7567_HEIGHT - 1, 1);
  }
  for (uint16_t y = 0; y < ST7567_HEIGHT; y++) {
    ST7567_DrawPixel(d, 0, (uint8_t)y, 1);
    ST7567_DrawPixel(d, ST7567_WIDTH - 1, (uint8_t)y, 1);
  }
  for (uint16_t x = 0; x < ST7567_WIDTH; x += 8) {
    for (uint16_t y = 2; y < 7; y++) {
      ST7567_DrawPixel(d, (uint8_t)x, (uint8_t)y, 1);
    }
  }
  for (uint16_t y = 0; y < ST7567_HEIGHT; y += 8) {
    for (uint16_t x = 2; x < 7; x++) {
      ST7567_DrawPixel(d, (uint8_t)x, (uint8_t)y, 1);
    }
  }

#elif PATTERN == PAT_ALLON
  ST7567_Fill(d);

#elif PATTERN == PAT_GRID8
  for (uint16_t y = 0; y < ST7567_HEIGHT; y++) {
    for (uint16_t x = 0; x < ST7567_WIDTH; x++) {
      if ((((x / 8) + (y / 8)) & 1u) == 0u) {
        ST7567_DrawPixel(d, (uint8_t)x, (uint8_t)y, 1);
      }
    }
  }

#elif PATTERN == PAT_CORNERS
  ST7567_DrawPixel(d, 0, 0, 1);
  ST7567_DrawPixel(d, ST7567_WIDTH - 1, 0, 1);
  ST7567_DrawPixel(d, 0, ST7567_HEIGHT - 1, 1);
  ST7567_DrawPixel(d, ST7567_WIDTH - 1, ST7567_HEIGHT - 1, 1);
  ST7567_DrawPixel(d, ST7567_WIDTH / 2, ST7567_HEIGHT / 2, 1);
#endif

#if SPEED_SWEEP
  /* Which speed step this is, as a bar whose length counts it: 1 block = 9 MHz,
   * 2 = 4.5, 3 = 2.25, 4 = 1.1, 5 = 0.56, 6 = 0.28 MHz.
   *
   * It lives in the bottom four rows, which are blanked right across first.
   * The pattern above it therefore stays untouched - put the marker in the
   * middle of the stripes and you cannot tell a real seam from the marker,
   * which defeats the point of the test. */
  for (uint16_t y = ST7567_HEIGHT - 4; y < ST7567_HEIGHT; y++) {
    for (uint16_t x = 0; x < ST7567_WIDTH; x++) {
      ST7567_DrawPixel(d, (uint8_t)x, (uint8_t)y, 0);
    }
  }
  for (uint16_t t = 0; t <= speed_step; t++) {
    for (uint16_t i = 0; i < 5; i++) {
      for (uint16_t y = ST7567_HEIGHT - 3; y < ST7567_HEIGHT - 1; y++) {
        ST7567_DrawPixel(d, (uint8_t)(2 + t*7 + i), (uint8_t)y, 1);
      }
    }
  }
#else
  (void)speed_step;
#endif
}

static void draw_pattern(uint8_t speed_step)
{
#if PANELS != PANEL_TWO
  build_pattern(&lcd1, speed_step);
  ST7567_Update(&lcd1);
#else
  ST7567_Clear(&lcd1);
  ST7567_Update(&lcd1);
#endif

#if PANELS != PANEL_ONE
  build_pattern(&lcd2, speed_step);
  ST7567_Update(&lcd2);
#else
  ST7567_Clear(&lcd2);
  ST7567_Update(&lcd2);
#endif
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

  /* USER CODE END 2 */

  /* USER CODE BEGIN WHILE */
  while (1)
  {
#if SPEED_SWEEP
    for (uint8_t step = 0; step < SPEED_COUNT; step++)
    {
      /* New speed, then a clean start, so each step is an independent test and
       * damage done at one speed cannot be blamed on the next. */
      spi_set_speed(SPEEDS[step]);
      panels_bring_up();

      for (uint32_t t = 0; t < DWELL_MS; t += REDRAW_MS) {
        draw_pattern(step);
        HAL_Delay(REDRAW_MS);
      }
    }
#else
    panels_bring_up();
    while (1) {
      draw_pattern(0);
      HAL_Delay(REDRAW_MS);
    }
#endif
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
