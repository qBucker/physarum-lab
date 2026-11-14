/*
 * ads1115_logger.ino
 * ------------------
 * 黏菌实验阶段 0：ADS1115 + Arduino Nano 串口记录器。
 *
 * 硬件：
 *   ADS1115  VDD -> 5V, GND -> GND, SCL -> A5, SDA -> A4, ADDR -> GND (0x48)
 *   A0/A1    -> 差分输入（默认 diff01）或 A0 单端
 *   D8       -> LED（串 220Ω）用于相机同步标记
 *
 * 串口命令（115200）：
 *   s        开始输出
 *   p        暂停输出
 *   m        标记：LED 亮 10 s（默认），同时 CSV 的 marker 列为 1
 *   d        差分模式（A0-A1，默认）
 *   u        单端模式（A0）
 *   g0..g5   增益：0=±6.144V, 1=±4.096V, 2=±2.048V,
 *                    3=±1.024V, 4=±0.512V, 5=±0.256V
 *   i        打印当前设置
 *
 * 输出 CSV：
 *   micros,mode,raw,mV,marker
 *
 * 依赖：Adafruit ADS1X15（库管理器安装，连带 Adafruit BusIO）
 */

#include <Wire.h>
#include <Adafruit_ADS1X15.h>

Adafruit_ADS1115 ads;

const int LED_PIN = 8;
// 同步标记亮灯时长：默认 10 s（相机 1 帧/10 s 时保证拍到）。
// 若相机 1 帧/分钟，需改成 >=60 s，或把相机间隔改成 10 s。
const uint32_t MARKER_MS = 10000;

bool streaming = true;
bool differential = true;
uint8_t gainIndex = 5;              // 默认 GAIN_SIXTEEN（±0.256 V，7.8 µV/LSB）
uint32_t markerUntil = 0;

// 满量程（mV），与 gainIndex 一一对应
const float fs_mV[6] = {6144.0, 4096.0, 2048.0, 1024.0, 512.0, 256.0};
const adsGain_t gainTable[6] = {
  GAIN_TWOTHIRDS, GAIN_ONE, GAIN_TWO, GAIN_FOUR, GAIN_EIGHT, GAIN_SIXTEEN
};

void applyGain() {
  ads.setGain(gainTable[gainIndex]);
}

void printInfo() {
  Serial.print("# INFO gain=");
  Serial.print(gainIndex);
  Serial.print(" fs_mV=");
  Serial.print(fs_mV[gainIndex], 0);
  Serial.print(" mode=");
  Serial.print(differential ? "diff01" : "single0");
  Serial.print(" rate=128SPS");
  Serial.println();
}

void setup() {
  pinMode(LED_PIN, OUTPUT);
  digitalWrite(LED_PIN, LOW);
  Serial.begin(115200);
  Wire.begin();

  if (!ads.begin()) {
    Serial.println("# ERROR ADS1115 not found (check wiring/address)");
    while (true) {
      digitalWrite(LED_PIN, !digitalRead(LED_PIN));
      delay(200);
    }
  }

  ads.setDataRate(RATE_ADS1115_128SPS);
  applyGain();
  Serial.println("# READY");
  printInfo();
}

void loop() {
  // 串口命令
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
      digitalWrite(LED_PIN, HIGH);
      Serial.println("# MARKER");
    } else if (c == 'u') {
      differential = false;
      printInfo();
    } else if (c == 'd') {
      differential = true;
      printInfo();
    } else if (c == 'g') {
      // 等待一个数字
      uint32_t t0 = millis();
      while (!Serial.available() && millis() - t0 < 1000) { /* wait */ }
      if (Serial.available()) {
        char g = Serial.read();
        if (g >= '0' && g <= '5') {
          gainIndex = (uint8_t)(g - '0');
          applyGain();
          printInfo();
        }
      }
    } else if (c == 'i') {
      printInfo();
    }
  }

  // 标记结束
  if (markerUntil != 0 && millis() >= markerUntil) {
    digitalWrite(LED_PIN, LOW);
    markerUntil = 0;
  }

  if (!streaming) {
    delay(10);
    return;
  }

  int16_t raw = differential ? ads.readADC_Differential_0_1()
                             : ads.readADC_SingleEnded(0);
  float mV = (float)raw * fs_mV[gainIndex] / 32768.0;
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

  // 128 SPS 由 ADS1115 转换时间自然限速；这里不再 delay。
}
