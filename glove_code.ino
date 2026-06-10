#include <SPI.h>
#include <nRF24L01.h>
#include <RF24.h>

RF24 radio(7, 8); // CE, CSN pins
const byte address[6] = "00001";

// Only defining the Index pin because you only have the index sensor connected!
const int indexPin = A1;

struct GloveData {
  int t; int i; int m; int r; int p;
};

void setup() {
  Serial.begin(9600);
  if (!radio.begin()) {
    Serial.println("GLOVE NRF24L01 MODULE NOT RESPONDING! Check wiring.");
    while (1) {} // Stop here if radio fails
  }
  radio.setAutoAck(true);
  radio.setRetries(15, 15);
  radio.openWritingPipe(address);
  radio.setPALevel(RF24_PA_MIN); 
  radio.stopListening();
  Serial.println("Glove Radio Initialized Successfully. Only reading Index Finger.");
}

void loop() {
  GloveData data;
  
  // Read and map ONLY the Index sensor
  data.i = map(analogRead(indexPin), 100, 60, 30, 170); 
  data.i = constrain(data.i, 30, 170);
  
  // Because the other flex sensors are NOT connected, reading them would cause 
  // random noise/jitter. So we FORCE them to stay open (30 degrees).
  data.t = 30; 
  data.m = 30; 
  data.r = 30; 
  data.p = 30;

  radio.write(&data, sizeof(GloveData));
  
  Serial.print("Sending Index: ");
  Serial.println(data.i);

  delay(50); // 20 updates per second
}
