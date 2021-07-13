#include "main.hpp"

bool ready_to_send = false;
bool measurement_ready = false;
bool make_next_measurement = true;
uint16_t manual_tim2_prescaler = 0;
uint8_t is_next = 0;
uint8_t measurements_A_B = 0;
char control_A_B = 'A';
uint16_t conversions = 0;
uint16_t single_measurement = 0;
uint16_t chan = 8;
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
    Serial.flush();
}

void setup() {
    Serial.begin(115200);
    // Measure 4 times and change
    pinMode(A0, INPUT);
    pinMode(A1, INPUT);
    pinMode(A2, INPUT);
    pinMode(A3, INPUT);
    pinMode(A4, INPUT);
    pinMode(A5, INPUT);
    pinMode(A6, INPUT);
    pinMode(A7, INPUT);
    // Measure Vref_A
    pinMode(A8, INPUT);
    // Measure Vref_B
    pinMode(A9, INPUT);

    // A control line
    // The word order is {5 4 3 2 <- [LSB]} and will be varied in a counting style (0000, 0001, 0010, 00011, ...)
    pinMode(2, OUTPUT);
    pinMode(3, OUTPUT);
    pinMode(4, OUTPUT);
    pinMode(5, OUTPUT);

    // B control line
    // The word order is {9 8 7 6 <- [LSB]} and will be varied in a counting style (0000, 0001, 0010, 00011, ...)
    pinMode(6, OUTPUT);
    pinMode(7, OUTPUT);
    pinMode(8, OUTPUT);
    pinMode(9, OUTPUT);

    delay(200);
    first_setup();
}

void loop() {
    if (make_next_measurement && !matrix_measurement.is_full()) {
        // Execution halts here until conversion is done
        // Starts new conversion
        make_conversion();
        make_next_measurement = false;
    } else if (measurement_ready) {
        noInterrupts();
        chan = next_chan(chan);
        change_analog_in(chan & 0xF);
        next_mux();
        matrix_measurement.push_value(single_measurement);
        ++conversions;
        interrupts();
        measurement_ready = false;
    } else if (conversions == 34) {
        noInterrupts();
        matrix_measurement.serial_transaction();
        interrupts();
        conversions = 0;
        ready_to_send = false;
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
    // Each tick takes 64us
    // Counts up to 125 -> 8ms
    OCR2A = 125;
    TCNT2 = 0;

    interrupts();
}

uint8_t next_chan (uint8_t chan) {
    if (is_next == 3 || chan > 7) {
        is_next = 0;
        ++chan;
    } else {
        ++is_next;
    }
    // Only analog inputs up to A9 will be used
    return chan % 10;
}

inline void next_mux () {
    // Only channels 0 to 7, that measure matrix sensors, need this multiplexing logic
    if (chan < 8) {
        // Create logic to multiplex line/col for A and B (they can be the same, since we will do a RR)
        if (measurements_A_B == 16) {
            measurements_A_B = 0;
            control_A_B = (control_A_B == 'A') ? 'B' : 'A';
        }
        uint8_t i = 0;
        if (control_A_B == 'A') {
            // 2,3,4,5
            for (i=0; i<4; i++) {
                digitalWrite(i+2, ((measurements_A_B & (1<<i)) == 0) ? LOW : HIGH);
            }
        } else {
            // 6,7,8,9
            for (i=0; i<4; i++) {
                digitalWrite(i+6, ((measurements_A_B & (1<<i)) == 0) ? LOW : HIGH);
            }
        }
        ++measurements_A_B;
    }
}

inline void change_analog_in (uint8_t chan) {
    // Forces a round robin
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
    // Makes 225 8ms interrupts -> 1800ms
    // Total turnaround: 34 sensors * 1800ms = 61.2s
    if (manual_tim2_prescaler == 225) {
        make_next_measurement = true;
        manual_tim2_prescaler = 0;
    }
    TCNT2 = 0;
}