/* USER CODE BEGIN Header */
/**
  ******************************************************************************
  * @file           : main.c
  * @brief          : Send a text message as a 2-bit optical code
  ******************************************************************************
  *
  * Encodes MESSAGE below into the two stacked panels, one static frame, for
  * reading back with screen_grid_capture_v8.py.
  *
  * FRAME FORMAT
  *   The grid is CODE_W x CODE_H cells, each carrying 2 bits, read row by row
  *   from the top left. Four cells make one byte, most significant bits
  *   first. With 8x8 pixel cells on a 128x64 panel that is 16 x 8 = 128
  *   cells = 32 bytes:
  *
  *     byte 0   0xA5   magic, so the reader can confirm it has the grid size
  *                     and orientation right before trusting anything else
  *     byte 1   len    number of text bytes that follow
  *     byte 2   crc    CRC-8 (polynomial 0x07) over the text bytes only
  *     byte 3+  text   the message, zero padded to the end of the frame
  *
  *   That leaves 29 characters at 16x8. Longer messages are truncated.
  *
  * CELL TO PANEL MAPPING
  *   cell value bit 0 -> panel 1        cell value bit 1 -> panel 2
  *   so   0 = both off      1 = panel 1 only
  *        2 = panel 2 only  3 = both on
  *
  *   The reader learns which physical brightness belongs to which value
  *   during calibration, so it does not matter whether value 1 ends up
  *   brighter or darker than value 2.
  *
  * BEFORE READING A MESSAGE
  *   Calibrate first: flash main_grid2x2.c with CELL_PX 8, press CALIBRATE
  *   in the Python tool, then flash this and press Save read.
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

/* ====== THE MESSAGE TO SEND ====== */
#define MESSAGE   "HELLO FROM STM32"

/* Cell size in panel pixels. 8 gives a 16 x 8 grid = 32 bytes.
 * Drop to 4 for 32 x 16 = 128 bytes once 8 reads reliably.
 * Must divide evenly into both 128 and 64. */
#define CELL_PX   8

#define CODE_W    (ST7567_WIDTH  / CELL_PX)
#define CODE_H    (ST7567_HEIGHT / CELL_PX)
#define CODE_BYTES ((CODE_W * CODE_H) / 4)   /* 4 cells per byte */

#define FRAME_MAGIC 0xA5
#define HEADER_LEN  3

/* ---- Orientation markers ----------------------------------------------
 * Set to 1 to reserve four cells carrying known states:
 *
 *     00 . . . . . . . . . . . . . . 01
 *      . . . . . . . . . . . . . . . .
 *      . 11 . . . . . . . . . . . . . .
 *     10 . . . . . . . . . . . . . . .
 *
 * Three corners used, the fourth left for payload, and 11 sitting one cell
 * diagonally in from 10. That asymmetry makes the arrangement chiral, so all
 * four rotations AND their mirrors are distinguishable - the reader can work
 * out which way up the frame is without being told.
 *
 * The markers are NOT good enough to supply the four reference colours. They
 * sit in the corners, where the lighting is most extreme: measured, two of
 * the four land further from their own state's true colour than the states
 * are from each other. Colour still has to come from calibration. Markers
 * answer "which way up", not "what colour".
 *
 * Cost is one byte: 28 characters instead of 29 at CELL_PX 8. The payload is
 * packed AROUND the reserved cells, so the header does not collide with them.
 *
 * The reader must be told which format a frame uses - it cannot tell by
 * looking, since marker cells look like any other cell. */
#define USE_MARKERS  1


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
 * it here moves the ADDRESS, so nothing is clipped - unlike shifting the
 * drawing, which pushes content off the edge and leaves a stray sliver.
 * If panel 2 is still out, try 0 or 8. */
#define PANEL1_COL_OFFSET   0
#define PANEL2_COL_OFFSET   4


/* ---- Resilience ---------------------------------------------------------
 * The frame used to be written to the panels exactly once, at boot. That is
 * precisely why a fault could look permanent and yet be different after every
 * reset: one corrupted byte on the SPI wire during that single write stays on
 * the glass until the next restart, and the next restart corrupts a different
 * byte. Nothing ever overwrites it.
 *
 * Writing the frame again every REFRESH_MS costs nothing on a static display
 * and turns a permanent defect into one that clears itself in well under a
 * second. Re-initialising every REINIT_MS covers the rarer case of a COMMAND
 * byte being hit, which can leave a whole page sitting at the wrong column.
 *
 * This is a safety net, not a cure. Fewer errors in the first place come from
 * SPI_PRESCALER below and from shorter, tidier wiring.
 */
#define REFRESH_MS      400
#define REINIT_MS       10000

/* SPI clock, set at boot so CubeMX does not have to be regenerated to change
 * it. On a 72 MHz APB2: _16 = 4.5 MHz (where this started), _64 = 1.1 MHz,
 * _128 = 560 kHz. Two panels hanging off the same SCK and SDI through
 * breadboard jumpers is a lot of capacitance for 4.5 MHz; the panel does not
 * care how slow it is, a static frame has all the time in the world. */
#define SPI_PRESCALER   SPI_BAUDRATEPRESCALER_64

/* USER CODE END PD */

/* USER CODE BEGIN PV */
static ST7567_t lcd1;
static ST7567_t lcd2;
static uint8_t  frame[CODE_BYTES];
/* USER CODE END PV */

void SystemClock_Config(void);
/* USER CODE BEGIN PFP */
static void panels_bring_up(void);
static void build_frame(const char *msg);
static void draw_frame(void);
/* USER CODE END PFP */

/* USER CODE BEGIN 0 */

/* Change only the clock divider, in place. Deliberately not HAL_SPI_DeInit()
 * followed by HAL_SPI_Init(): DeInit calls HAL_SPI_MspDeInit(), which switches
 * the SPI clock off and hands PA5 and PA7 back as plain GPIO - and those two
 * pins are shared with both panels. The SPI_BAUDRATEPRESCALER_* constants are
 * already positioned for the BR field of CR1, so they drop straight in. */
static void spi_set_speed(uint32_t prescaler)
{
  __HAL_SPI_DISABLE(&hspi1);
  MODIFY_REG(hspi1.Instance->CR1, SPI_CR1_BR, prescaler);
  hspi1.Init.BaudRatePrescaler = prescaler;
  __HAL_SPI_ENABLE(&hspi1);
}

/* CRC-8, polynomial 0x07. The Python reader uses the same. */
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

#if USE_MARKERS
/* Is this cell reserved for a marker, and if so which state does it carry? */
static int marker_state(uint16_t row, uint16_t col)
{
  if (row == 0 && col == 0)             return 0;
  if (row == 0 && col == CODE_W - 1)    return 1;
  if (row == CODE_H - 1 && col == 0)    return 2;
  if (row == CODE_H - 2 && col == 1)    return 3;
  return -1;
}
#define MARKER_COUNT 4
#else
#define MARKER_COUNT 0
#endif

/* Cells left for payload, and therefore how many whole bytes fit. */
#define PAYLOAD_CELLS  ((CODE_W * CODE_H) - MARKER_COUNT)
#define PAYLOAD_BYTES  (PAYLOAD_CELLS / 4)

static void build_frame(const char *msg)
{
  memset(frame, 0, sizeof(frame));

  uint16_t room = PAYLOAD_BYTES - HEADER_LEN;
  uint16_t n = (uint16_t)strlen(msg);
  if (n > room) {
    n = room;                 /* truncate rather than overrun */
  }

  frame[0] = FRAME_MAGIC;
  frame[1] = (uint8_t)n;
  memcpy(&frame[HEADER_LEN], msg, n);
  frame[2] = crc8(&frame[HEADER_LEN], n);
}

/* Paint one cell as a solid CELL_PX square on whichever panels its bits ask
 * for. Cell index runs row by row from the top left. */
/* ---- Cell geometry -------------------------------------------------------
 * Both panels are drawn at the same scale: cell (cx, cy) is simply the
 * CELL_PX square at (cx*CELL_PX, cy*CELL_PX) on whichever panels its bits ask
 * for. Every cell is exactly CELL_PX across, every edge meets its neighbour,
 * and the grid runs flush to the glass on both panels.
 */
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

/* Bring both panels up in a way that survives a warm reset.
 *
 * Three things make a restart come out differently each time:
 *
 * 1. Between the MCU reset and MX_GPIO_Init(), every pin is a floating input.
 *    The panels never lose power on a warm reset, so they are still listening,
 *    and whatever they pick up in that window can leave one mid-command. Both
 *    chip selects are therefore driven HIGH before anything else happens, so
 *    neither panel is listening while things settle.
 *
 * 2. Both panels share SCK, SDI and DC. If one chip select is low while the
 *    other panel is being set up, BOTH receive that panel's commands -
 *    including the wrong segment direction and column offset. CubeMX must
 *    have PA3 and PA1 set to an initial level of High; if it does not, this
 *    happens on every boot and the second panel ends up misconfigured.
 *
 * 3. On a cold start the panel's own supply may still be rising when the MCU
 *    is already running, so early commands are simply ignored. A short wait
 *    before the first command costs nothing on a static display.
 *
 * Initialising twice is cheap insurance: the second pass runs with everything
 * powered and quiet, so it lands even if the first was disturbed. */
static void panels_bring_up(void)
{
  /* Nobody is listening until we say so. */
  HAL_GPIO_WritePin(LCD1_CS_PORT, LCD1_CS_PIN, GPIO_PIN_SET);
  HAL_GPIO_WritePin(LCD2_CS_PORT, LCD2_CS_PIN, GPIO_PIN_SET);
  HAL_GPIO_WritePin(LCD_DC_PORT,  LCD_DC_PIN,  GPIO_PIN_SET);

  /* Hold both panels in reset together, then let them out. */
  HAL_GPIO_WritePin(LCD1_RST_PORT, LCD1_RST_PIN, GPIO_PIN_RESET);
  HAL_GPIO_WritePin(LCD2_RST_PORT, LCD2_RST_PIN, GPIO_PIN_RESET);
  HAL_Delay(50);
  HAL_GPIO_WritePin(LCD1_RST_PORT, LCD1_RST_PIN, GPIO_PIN_SET);
  HAL_GPIO_WritePin(LCD2_RST_PORT, LCD2_RST_PIN, GPIO_PIN_SET);
  HAL_Delay(150);          /* let the panel supplies settle */

  for (int pass = 0; pass < 2; pass++) {
    ST7567_Init(&lcd1);
    HAL_Delay(20);
    ST7567_Init(&lcd2);
    HAL_Delay(20);
  }
}

static void draw_frame(void)
{
  ST7567_Clear(&lcd1);
  ST7567_Clear(&lcd2);

  /* Walk the grid in reading order. Reserved cells get their marker state;
   * every other cell takes the next two bits of the payload. Packing around
   * the markers is what stops them colliding with the header. */
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

  build_frame(MESSAGE);

  /* USER CODE END 2 */

  /* USER CODE BEGIN WHILE */
  uint32_t last_reinit = HAL_GetTick();

  while (1)
  {
    /* Rewrite the same frame, over and over. Identical bytes, so nothing moves
     * on screen unless the previous write was damaged - in which case this is
     * what repairs it. */
    draw_frame();
    HAL_Delay(REFRESH_MS);

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
