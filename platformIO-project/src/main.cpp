#include "main.hpp"

bool measurement_ready = false;
bool ready_to_send = false;
uint8_t manual_tim2_prescaler = 0;
uint16_t conversions = 0;
uint16_t single_measurement = 0;
uint16_t chan = 0;
ADC_RESULT matrix_measurement;

bool ADC_RESULT::is_empty () {
    if (index == -1) {
        return true;
    }
    else {
        return false;
    }
}

ADC_RESULT::ADC_RESULT(){
    max_size = (int) N_SENSORS;
    index = -1;
}

bool ADC_RESULT::is_full () {
    if (index == max_size-1) {
        return true;
    }
    else {
        return false;
    }
}

void ADC_RESULT::push_value (uint16_t value){
    if (index < max_size-1)
        data[++index] = value;
}

uint16_t ADC_RESULT::pop_value (){
    if (index >= 0){
        return data[index--];
    }
    else {
        index = -1;
        return index;
    }
}

void ADC_RESULT::serial_transaction (){
    char output [N_SENSORS*16+1];
    char *out_ptr = output;
    while (! is_empty()){
        out_ptr += sprintf(out_ptr, "%04u|",pop_value());
    }
    Serial.println(output);
}

void setup() {
    Serial.begin(115200);
    pinMode(A0, INPUT);
    pinMode(A1, INPUT);
    pinMode(A2, INPUT);
    pinMode(A3, INPUT);
    pinMode(A4, INPUT);
    pinMode(A5, INPUT);
    pinMode(A6, INPUT);
    pinMode(A7, INPUT);
    pinMode(A8, INPUT);
    pinMode(A9, INPUT);
    pinMode(A10, INPUT);
    pinMode(A11, INPUT);
    pinMode(A12, INPUT);
    pinMode(A13, INPUT);
    pinMode(A14, INPUT);
    pinMode(A15, INPUT);
    delay(200);
    first_setup();
}

void loop() {
    // Execution should halt here until conversion is done
    change_analog_in(chan & 0xF);
    if (measurement_ready) {
        noInterrupts();
        ++chan;
        matrix_measurement.push_value(single_measurement);
        interrupts();
        measurement_ready = false;
    } else if (ready_to_send) {
        noInterrupts();
        matrix_measurement.serial_transaction();
        Serial.flush();
        interrupts();
        ready_to_send = false;
    } else if (!matrix_measurement.is_full()) {
        // Starts new conversion
        make_conversion();
    }
}

void first_setup () {
    noInterrupts();

    // Reference is VCC with 100uF capacitor between AREF and ground
    uint8_t admux_setup = 1 << REFS0;
    ADMUX = admux_setup;

    uint8_t adcsra_setup = (1<<ADEN);
    adcsra_setup |= (1<<ADIE);

    // 128 pre-scale -> 125kHz
    // Each measurement takes 
    //     If on ADC noise reduction mode: 13*T = 104us
    adcsra_setup |= (1<<ADPS2);
    adcsra_setup |= (1<<ADPS1);
    adcsra_setup |= (1<<ADPS0);
    ADCSRA = adcsra_setup;

    sleep_enable();
    set_sleep_mode(SLEEP_MODE_ADC);

    DIDR0 = 0xFF;
    DIDR1 = 0xFF;
    DIDR2 = 0xFF;

    // This is an 8 bit Timer
    TCCR2A ^= TCCR2A;
    TCCR2B ^= TCCR2B;
    // CTC mode
    TCCR2A |= (1<<WGM21);
    // clk(io)/1024 for Timer2
    TCCR2B |= (1<<CS22);
    TCCR2B |= (1<<CS21);
    TCCR2B |= (1<<CS20);
    TIMSK2 |= (1<<OCIE2A);
    // Counts up to 250 -> 16ms
    OCR2A = 250;
    TCNT2 = 0;

    interrupts();
}

inline void change_analog_in (uint8_t chan) {
    // Forces a round robin. It takes advantage of chan overflowing
    uint8_t high_ADMUX = ADMUX & 0xF0;
    if (chan < 8) {
        chan = chan & 0x07;
        ADMUX = high_ADMUX | (chan & 0x0F);
        ADCSRB &= ~(1<<MUX5);
    } else {
        chan = chan & 0x07;
        ADMUX = high_ADMUX | (chan & 0x0F);
        ADCSRB |= (1<<MUX5);
    }
}

inline void make_conversion () {
    interrupts();
    sleep_cpu();
}

ISR(ADC_vect) {
    measurement_ready = true;
    single_measurement = ADC;
}

ISR(TIMER2_COMPA_vect) {
    ++manual_tim2_prescaler;
    // Makes 6 16ms interrupts -> 0.096s ~ 0.1s
    if (manual_tim2_prescaler == 6) {
        ready_to_send = true;
        manual_tim2_prescaler = 0;
    }
    TCNT2 = 0;
}