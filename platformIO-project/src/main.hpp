#include <Arduino.h>
#include <avr/sleep.h>
#define N_SENSORS 16

class ADC_RESULT {
  uint16_t data [N_SENSORS];
  int max_size;
  private:
    bool is_empty ();
  public:
    int index;
    ADC_RESULT();
    bool is_full ();
    void push_value (uint16_t value);
    uint16_t pop_value ();
    void serial_transaction ();
};

void first_setup ();
inline void change_analog_in (uint8_t chan);
inline void make_conversion ();