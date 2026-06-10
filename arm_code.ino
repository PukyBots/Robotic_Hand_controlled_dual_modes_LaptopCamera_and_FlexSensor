#include <Servo.h>
#include <SPI.h>
#include <nRF24L01.h>
#include <RF24.h>

Servo thumb, indexF, middle, ring, pinky;

RF24 radio(7, 8); // CE, CSN pins on Robot Arduino
const byte address[6] = "00001";

struct GloveData {
  int t; int i; int m; int r; int p;
};

// Start in CV mode by default, wait for Python to tell us otherwise
String currentMode = "CV"; 

void setup() {
  Serial.begin(9600);
  
  // Attach Servo signal pins 
  // MATCHING YOUR CIRCUIT DIAGRAM:
  thumb.attach(5);   // Thumb -> D5
  indexF.attach(3);  // Index -> D3
  middle.attach(6);  // Middle -> D6
  ring.attach(9);    // Ring -> D9
  pinky.attach(10);  // Pinky -> D10

  if (!radio.begin()) {
    Serial.println("ARM NRF24L01 MODULE NOT RESPONDING! Check wiring.");
  } else {
    Serial.println("Arm Radio Initialized Successfully.");
  }
  
  radio.setAutoAck(true);
  radio.openReadingPipe(1, address);
  radio.setPALevel(RF24_PA_MIN);
  radio.startListening();
}

void loop() {
  // 1. Check for commands or Camera Data from the Python script
  if (Serial.available() > 0) {
    String input = Serial.readStringUntil('\n');
    input.trim();
    
    if (input == "MODE:CV") {
      currentMode = "CV";
    } else if (input == "MODE:GLOVE") {
      currentMode = "GLOVE";
    } else if (currentMode == "CV") {
      // Parse CSV: t,i,m,r,p
      int firstComma = input.indexOf(',');
      int secondComma = input.indexOf(',', firstComma + 1);
      int thirdComma = input.indexOf(',', secondComma + 1);
      int fourthComma = input.indexOf(',', thirdComma + 1);
      
      if (firstComma != -1 && secondComma != -1 && thirdComma != -1 && fourthComma != -1) {
        int t = input.substring(0, firstComma).toInt();
        int i = input.substring(firstComma + 1, secondComma).toInt();
        int m = input.substring(secondComma + 1, thirdComma).toInt();
        int r = input.substring(thirdComma + 1, fourthComma).toInt();
        int p = input.substring(fourthComma + 1).toInt();
        
        thumb.write(t);
        indexF.write(i);
        middle.write(m);
        ring.write(r);
        pinky.write(p);
      }
    }
  }

  // 2. Listen for Glove (When Python script says so)
  if (currentMode == "GLOVE") {
    if (radio.available()) {
      GloveData data;
      radio.read(&data, sizeof(GloveData));
      
      thumb.write(data.t);
      indexF.write(data.i);
      middle.write(data.m);
      ring.write(data.r);
      pinky.write(data.p);
      
      // Send to python for simulation update
      Serial.print("GLOVE:");
      Serial.print(data.t); Serial.print(",");
      Serial.print(data.i); Serial.print(",");
      Serial.print(data.m); Serial.print(",");
      Serial.print(data.r); Serial.print(",");
      Serial.println(data.p);
    }
  }
}
