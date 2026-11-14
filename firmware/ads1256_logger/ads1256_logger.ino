/*
 * ads1256_logger.ino
 * ------------------
 * 黏菌实验阶段 0：ADS1256 + ESP32 串口记录器。
 *
 * 硬件（凌智电子 ADS1256-24位8通道AD模块 V1.1）：
 *   ADS1256  VCC -> 5V, GND -> GND
 *   SCLK -> GPIO18, DIN(MOSI) -> GPIO23, DOUT(MISO) -> GPIO19
 *   CS   -> GPIO5,  DRDY -> GPIO4,  RESET -> GPIO27
 *   AIN0/AIN1 -> 差分输入（AINCOM 跳线 J1 拔掉）
 *   GPIO32 -> LED（串 220Ω）用于相机同步标记
 *
 * 关键配置（不要照抄厂商 STM32 例程）：
 *   - buffer ON（STATUS BUFEN=1）；厂商例程默认关闭
 *   - 差分 AIN0-AIN1（MUX=0x01）；厂商例程默认 AIN0-AINCOM
 *   - VREF=2.5V、无分压：满量程 ±2.5V/PGA；厂商代码按 5V 基准写，换算会大 2 倍
 *   - 10 SPS（50/60 Hz 抑制）；T4 的 50 Hz 用 1 kSPS 单独跑
 *
 * 串口命令（921600；1 kSPS 时 115200 会限速）：
 *   s        开始输出
 *   p        暂停输出
 *   m        标记：LED 亮 10 s，CSV marker=1
 *   d        差分 AIN0-AIN1（默认）
 *   u        单端 AIN0-AINCOM（需短接 J1 跳线）
 *   g0..g6   PGA：0=1, 1=2, 2=4, 3=8, 4=16, 5=32, 6=64
 *   t0/t1    数据率：t0=10 SPS（默认），t1=1000 SPS（T4 用）
 *   i        打印当前设置
 *
 * 输出 CSV：
 *   micros,mode,raw,mV,marker
 *
 * 依赖：ESP32 Arduino core（SPI 库）
 */

#include <SPI.h>

// ---------- pins ----------
const int PIN_SCK   = 18;
const int PIN_MISO  = 19;
const int PIN_MOSI  = 23;
const int PIN_CS    = 5;
const int PIN_DRDY  = 4;
const int PIN_RESET = 27;
const int PIN_LED   = 32;

// ---------- ADS1256 registers / commands ----------
const uint8_t REG_STATUS = 0x00;
const uint8_t REG_MUX    = 0x01;
const uint8_t REG_ADCON  = 0x02;
const uint8_t REG_DRATE  = 0x03;

const uint8_t CMD_RDATA   = 0x01;
const uint8_t CMD_RDATAC  = 0x03;
const uint8_t CMD_SDATAC  = 0x0F;
const uint8_t CMD_WREG    = 0x50;
const uint8_t CMD_SELFCAL = 0xF0;
const uint8_t CMD_RESET   = 0xFE;

// DRATE values: 10 SPS = 0x23, 1000 SPS = 0xA1 (see ADS1256 datasheet)
const uint8_t DRATE_10SPS   = 0x23;
const uint8_t DRATE_1000SPS = 0xA1;

// MUX: AIN0 positive, AIN1 negative; AIN0 positive, AINCOM negative
const uint8_t MUX_DIFF01  = 0x01;
const uint8_t MUX_SINGLE0 = 0x08;

// ---------- state ----------
// PGA index 0..6 -> gain 1,2,4,8,16,32,64
uint8_t pgaIndex = 3;          // default PGA=8, full scale ±312.5 mV
uint8_t drateCode = DRATE_10SPS;
bool differential = true;
bool streaming = true;
uint32_t markerUntil = 0;

const uint32_t MARKER_MS = 10000;  // camera 1 frame/10 s

int pgaGain() {
  return 1 << pgaIndex;
}

// VREF = 2.5 V, no divider: LSB = VREF / (PGA * 2^23) [mV]
float lsbMv() {
  return 2500.0f / (pgaGain() * 8388608.0f);
}

float fullScaleMv() {
  return 2500.0f / pgaGain();
}

uint32_t sampleRate() {
  return (drateCode == DRATE_1000SPS) ? 1000 : 10;
}

// ---------- low-level SPI ----------
void sendCommand(uint8_t cmd) {
  digitalWrite(PIN_CS, LOW);
  SPI.transfer(cmd);
  digitalWrite(PIN_CS, HIGH);
  delayMicroseconds(10);
}

void writeRegister(uint8_t reg, uint8_t value) {
  digitalWrite(PIN_CS, LOW);
  SPI.transfer(CMD_WREG | (reg & 0x0F));
  SPI.transfer(0x00);  // count-1 = 0 -> one register
  SPI.transfer(value);
  digitalWrite(PIN_CS, HIGH);
  delayMicroseconds(10);
}

bool waitDRDY(uint32_t timeout_ms) {
  uint32_t t0 = millis();
  while (digitalRead(PIN_DRDY) == HIGH) {
    if (millis() - t0 > timeout_ms) return false;
    delay(1);
  }
  return true;
}

// Write STATUS, MUX, ADCON, DRATE in one WREG.
void writeConfig() {
  uint8_t status = 0xF6;  // ID=1111, ORDER=0, ACAL=1, BUFEN=1
  uint8_t mux = differential ? MUX_DIFF01 : MUX_SINGLE0;
  uint8_t adcon = (uint8_t)(pgaIndex & 0x07);  // CLKOUT off, sensor detect off, PGA

  sendCommand(CMD_SDATAC);
  delay(5);
  digitalWrite(PIN_CS, LOW);
  SPI.transfer(CMD_WREG | 0x00);
  SPI.transfer(0x03);  // 4 registers
  SPI.transfer(status);
  SPI.transfer(mux);
  SPI.transfer(adcon);
  SPI.transfer(drateCode);
  digitalWrite(PIN_CS, HIGH);
  delay(10);
}

bool calibrate() {
  sendCommand(CMD_SELFCAL);
  delay(200);
  return waitDRDY(3000);
}

void startContinuous() {
  sendCommand(CMD_RDATAC);
}

void resetADS() {
  digitalWrite(PIN_CS, HIGH);
  digitalWrite(PIN_RESET, LOW);
  delay(20);
  digitalWrite(PIN_RESET, HIGH);
  delay(1000);
}

bool configure() {
  sendCommand(CMD_RESET);
  delay(1000);
  writeConfig();
  if (!calibrate()) return false;
  startContinuous();
  return true;
}

int32_t readData() {
  digitalWrite(PIN_CS, LOW);
  uint32_t b0 = SPI.transfer(0x00);
  uint32_t b1 = SPI.transfer(0x00);
  uint32_t b2 = SPI.transfer(0x00);
  digitalWrite(PIN_CS, HIGH);

  int32_t v = (int32_t)((b0 << 16) | (b1 << 8) | b2);
  if (v & 0x800000) v -= 0x1000000;  // sign-extend 24-bit
  return v;
}

// ---------- serial ----------
void printInfo() {
  Serial.print("# INFO adc=ADS1256 pga_index=");
  Serial.print(pgaIndex);
  Serial.print(" pga=");
  Serial.print(pgaGain());
  Serial.print(" rate=");
  Serial.print(sampleRate());
  Serial.print("SPS vref_mV=2500 buffer=1 mux=");
  Serial.print(differential ? "diff01" : "single0");
  Serial.print(" full_scale_mV=");
  Serial.print(fullScaleMv(), 3);
  Serial.print(" lsb_uV=");
  Serial.print(lsbMv() * 1000.0f, 6);
  Serial.println();
}

void setDataRate(uint8_t code) {
  drateCode = code;
  sendCommand(CMD_SDATAC);
  writeRegister(REG_DRATE, drateCode);
  if (!calibrate()) Serial.println("# ERROR self-cal timeout");
  startContinuous();
  printInfo();
}

// ---------- setup / loop ----------
void setup() {
  pinMode(PIN_LED, OUTPUT);
  digitalWrite(PIN_LED, LOW);
  Serial.begin(921600);
  delay(100);

  pinMode(PIN_CS, OUTPUT);
  digitalWrite(PIN_CS, HIGH);
  pinMode(PIN_DRDY, INPUT);
  pinMode(PIN_RESET, OUTPUT);
  digitalWrite(PIN_RESET, HIGH);

  SPI.begin(PIN_SCK, PIN_MISO, PIN_MOSI, PIN_CS);
  SPI.beginTransaction(SPISettings(1000000, MSBFIRST, SPI_MODE1));

  resetADS();
  if (!configure()) {
    Serial.println("# ERROR ADS1256 not responding (check 5V/GND, SPI, DRDY, RESET)");
    while (true) {
      digitalWrite(PIN_LED, !digitalRead(PIN_LED));
      delay(200);
    }
  }

  Serial.println("# READY");
  printInfo();
}

void loop() {
  while (Serial.available() > 0) {
    char c = Serial.read();

    if (c == 's') {
      streaming = true;
      Serial.println("# STREAM ON");
    } else if (c == 'p') {
      streaming = false;
      Serial.println("# STREAM OFF");
    } else if (c == 'm') {
      markerUntil = millis() + MARKER_MS;
      digitalWrite(PIN_LED, HIGH);
      Serial.println("# MARKER");
    } else if (c == 'd') {
      differential = true;
      sendCommand(CMD_SDATAC);
      writeRegister(REG_MUX, MUX_DIFF01);
      startContinuous();
      printInfo();
    } else if (c == 'u') {
      differential = false;
      sendCommand(CMD_SDATAC);
      writeRegister(REG_MUX, MUX_SINGLE0);
      startContinuous();
      printInfo();
    } else if (c == 'g') {
      uint32_t t0 = millis();
      while (!Serial.available() && millis() - t0 < 1000) { /* wait */ }
      if (Serial.available()) {
        char g = Serial.read();
        if (g >= '0' && g <= '6') {
          pgaIndex = (uint8_t)(g - '0');
          sendCommand(CMD_SDATAC);
          writeRegister(REG_ADCON, (uint8_t)(pgaIndex & 0x07));
          if (!calibrate()) Serial.println("# ERROR self-cal timeout");
          startContinuous();
          printInfo();
        }
      }
    } else if (c == 't') {
      uint32_t t0 = millis();
      while (!Serial.available() && millis() - t0 < 1000) { /* wait */ }
      if (Serial.available()) {
        char t = Serial.read();
        if (t == '0') {
          setDataRate(DRATE_10SPS);
        } else if (t == '1') {
          setDataRate(DRATE_1000SPS);
        }
      }
    } else if (c == 'i') {
      printInfo();
    }
  }

  if (markerUntil != 0 && millis() >= markerUntil) {
    digitalWrite(PIN_LED, LOW);
    markerUntil = 0;
  }

  if (!streaming) {
    delay(10);
    return;
  }

  if (digitalRead(PIN_DRDY) == LOW) {
    int32_t raw = readData();
    float mV = (float)raw * lsbMv();
    uint32_t t = micros();
    uint8_t marker = (markerUntil != 0) ? 1 : 0;

    Serial.print(t);
    Serial.print(',');
    Serial.print(differential ? "diff01" : "single0");
    Serial.print(',');
    Serial.print(raw);
    Serial.print(',');
    Serial.print(mV, 6);
    Serial.print(',');
    Serial.println(marker);
  }
}
