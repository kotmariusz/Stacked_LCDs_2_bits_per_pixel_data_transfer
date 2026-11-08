/* USER CODE BEGIN Header */
/**
  ******************************************************************************
  * @file           : main.c
  * @brief          : Self-test cycle - four baselines then the real data
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
  * Cycles six phases forever:
  *
  *     MARKER -> solid 00 -> solid 01 -> solid 10 -> solid 11 -> DATA
  *
  * The reader watches one full cycle, learns what each state looks like at
  * every cell from the four solid phases, then decodes the DATA phase against
  * those baselines and checks the result with the CRC. One button, one
  * measurement, no separate calibration step.
  *
  * WHY THE MARKER IS STILL HERE
  *   The reader has to know which phase is which, and it cannot use the DATA
  *   frame to work that out. It finds phases by looking for the most detailed
  *   one, and a payload made of large uniform blocks is LESS detailed than a
  *   checkerboard - tested, it scored 0.9x against the solid frames and the
  *   sync failed. The marker is the only phase guaranteed to stand out.
  *
  *   The reader also trusts only the marker's boundary and steps through the
  *   rest by duration. Counting every transition breaks when a data frame
  *   happens to resemble the solid frame before it: that boundary becomes
  *   invisible, two phases merge, and everything after shifts by one. That
  *   failure took a 100% read down to 25% before it was fixed.
  *
  * DWELL
  *   Each phase is held DWELL_MS. The whole cycle is six phases, so at the
  *   default the reader needs about 15 seconds of capture per cycle and grabs
  *   a little over two cycles to be certain of catching a complete one.
  *
  *
  *   Moving the camera further away fixes the same problem for free: the
  *   error scales as gap divided by distance, so 5 cm to 20 cm cuts it
  *   fourfold. Worth trying before reaching for this.
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

/* ====== THE MESSAGE SENT IN THE DATA PHASE ====== */
#define MESSAGE     "HELLO FROM STM32"

#define DWELL_MS    2500
#define CELL_PX     8

/* 1000 = no correction. 1000 + 1000*gap/camera_distance otherwise. */
/* Which panel is further from the camera: 1 or 2. */

#define CODE_W      (ST7567_WIDTH  / CELL_PX)
#define CODE_H      (ST7567_HEIGHT / CELL_PX)
#define CODE_BYTES  ((CODE_W * CODE_H) / 4)

#define FRAME_MAGIC 0xA5
#define HEADER_LEN  3

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

#define LCD_CONTRAST    38

/* USER CODE END PD */

/* USER CODE BEGIN PV */
static ST7567_t lcd1;
static ST7567_t lcd2;
static uint8_t  frame[CODE_BYTES];
/* USER CODE END PV */

void SystemClock_Config(void);
/* USER CODE BEGIN PFP */
static void build_frame(const char *msg);
static void draw_marker(void);
static void draw_solid(uint8_t state);
static void draw_data(void);
/* USER CODE END PFP */

/* USER CODE BEGIN 0 */

/* CRC-8, polynomial 0x07, matching the reader. */
static uint8_t crc8(const uint8_t *data, uint16_t len)
{
  uint8_t crc = 0;
  for (uint16_t i = 0; i < len; i++) {
    crc ^= data[i];
    for (uint8_t b = 0; b < 8; b++) {
      crc = (crc & 0x80) ? (uint8_t)((crc << 1) ^ 0x07) : (uint8_t)(crc << 1);
    }
  }
  return crc;
}

static void build_frame(const char *msg)
{
  memset(frame, 0, sizeof(frame));

  uint16_t room = CODE_BYTES - HEADER_LEN;
  uint16_t n = (uint16_t)strlen(msg);
  if (n > room) {
    n = room;
  }
  frame[0] = FRAME_MAGIC;
  frame[1] = (uint8_t)n;
  memcpy(&frame[HEADER_LEN], msg, n);
  frame[2] = crc8(&frame[HEADER_LEN], n);
}

static void fill_cell(ST7567_t *d, uint16_t cx, uint16_t cy)
{
  ST7567_FillRect(d, (uint8_t)(cx * CELL_PX), (uint8_t)(cy * CELL_PX),
                  CELL_PX, CELL_PX, 1);
}

static void put_cell(uint16_t index, uint8_t value)
{
  uint16_t cx = index % CODE_W;
  uint16_t cy = index / CODE_W;

  if (value & 0x01) fill_cell(&lcd1, cx, cy);
  if (value & 0x02) fill_cell(&lcd2, cx, cy);
}

/* Alternating 2x2 cells - the most detailed phase, which is what makes it
 * findable whatever the payload looks like. */
static void draw_marker(void)
{
  ST7567_Clear(&lcd1);
  ST7567_Clear(&lcd2);
  for (uint16_t cy = 0; cy < CODE_H; cy++) {
    for (uint16_t cx = 0; cx < CODE_W; cx++) {
      put_cell((uint16_t)(cy * CODE_W + cx),
               (uint8_t)((cx % 2) + (cy % 2) * 2));
    }
  }
  ST7567_Update(&lcd1);
  ST7567_Update(&lcd2);
}

static void draw_solid(uint8_t state)
{
  ST7567_Clear(&lcd1);
  ST7567_Clear(&lcd2);
  /* Filled cell by cell rather than ST7567_Fill, so the far panel gets the
   * same magnification as the data phase. A solid field looks identical
   * either way, but the edges do not, and the reader measures the edges. */
  for (uint16_t cy = 0; cy < CODE_H; cy++) {
    for (uint16_t cx = 0; cx < CODE_W; cx++) {
      put_cell((uint16_t)(cy * CODE_W + cx), state);
    }
  }
  ST7567_Update(&lcd1);
  ST7567_Update(&lcd2);
}

static void draw_data(void)
{
  ST7567_Clear(&lcd1);
  ST7567_Clear(&lcd2);
  for (uint16_t b = 0; b < CODE_BYTES; b++) {
    uint8_t byte = frame[b];
    for (uint8_t k = 0; k < 4; k++) {
      uint8_t shift = (uint8_t)((3 - k) * 2);
      put_cell((uint16_t)(b * 4 + k), (uint8_t)((byte >> shift) & 0x03));
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
  lcd1.contrast = LCD_CONTRAST;
  lcd1.adc_cmd  = 0xA0;
  lcd1.com_cmd  = 0xC0;

  lcd2.hspi     = &hspi1;
  lcd2.cs_port  = LCD2_CS_PORT;   lcd2.cs_pin  = LCD2_CS_PIN;
  lcd2.dc_port  = LCD_DC_PORT;    lcd2.dc_pin  = LCD_DC_PIN;
  lcd2.rst_port = LCD2_RST_PORT;  lcd2.rst_pin = LCD2_RST_PIN;
  lcd2.contrast = LCD_CONTRAST;
  lcd2.adc_cmd  = 0xA1;
  lcd2.com_cmd  = 0xC0;

  ST7567_Init(&lcd1);
  ST7567_Init(&lcd2);

  build_frame(MESSAGE);

  /* USER CODE END 2 */

  /* USER CODE BEGIN WHILE */
  while (1)
  {
    draw_marker();
    HAL_Delay(DWELL_MS);

    for (uint8_t s = 0; s < 4; s++)
    {
      draw_solid(s);
      HAL_Delay(DWELL_MS);
    }

    draw_data();
    HAL_Delay(DWELL_MS);
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
