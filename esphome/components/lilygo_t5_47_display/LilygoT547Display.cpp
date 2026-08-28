#include "LilygoT547Display.h"
#include "esphome/core/log.h"

#define WAVEFORM EPD_BUILTIN_WAVEFORM

namespace esphome {
namespace lilygo_t5_47_display {

static const char *const TAG = "lilygo_t5_47_display";

float LilygoT547Display::get_setup_priority() const { return esphome::setup_priority::LATE; }

void LilygoT547Display::set_clear_screen(bool clear) { this->clear_ = clear; }
void LilygoT547Display::set_power_off_delay_enabled(bool power_off_delay_enabled) {
  this->power_off_delay_enabled_ = power_off_delay_enabled;
}
void LilygoT547Display::set_landscape(bool landscape) { this->landscape_ = landscape; }

void LilygoT547Display::set_temperature(uint32_t temperature) { this->temperature_ = temperature; }

int LilygoT547Display::get_width_internal() { return 960; }

int LilygoT547Display::get_height_internal() { return 540; }

void LilygoT547Display::setup() {
  // epd_init() heeft sinds epdiy 2.x drie argumenten. ED047TC1 is het juiste
  // paneel voor de T5 4.7" (960x540). Het lilygo-voorbeeld in de epdiy-repo
  // gebruikt ED097TC2, maar dat is het 9,7"-paneel.
  // epd_set_vcom() is niet nodig: set_vcom is NULL in epd_board_lilygo_t5_47,
  // VCOM ligt op dit bord in hardware vast.
  epd_init(&epd_board_lilygo_t5_47, &ED047TC1, EPD_OPTIONS_DEFAULT);
  hl = epd_hl_init(WAVEFORM);
  if (landscape_) {
    EpdRotation orientation = EPD_ROT_LANDSCAPE;
    epd_set_rotation(orientation);
  } else {
    EpdRotation orientation = EPD_ROT_PORTRAIT;
    epd_set_rotation(orientation);
  }
  fb = epd_hl_get_framebuffer(&hl);
}

void LilygoT547Display::update() {
  if (this->init_clear_executed_ == false && this->clear_ == true) {
    LilygoT547Display::full_clear();
    this->init_clear_executed_ = true;
  }
  this->do_update_();
  LilygoT547Display::flush_screen_changes();
}

// ESPHome's Display::clear() is een *buffer*-clear: hij wordt bij elke
// do_update_() aangeroepen als auto_clear aanstaat. Hier een hardware-wispuls
// doen (zoals upstream deed) geeft een volledige witflits bij iedere redraw.
void LilygoT547Display::clear() { epd_hl_set_all_white(&hl); }

// Hardware full clear: flitst het paneel wit. Alleen bij het opstarten, als
// "clear: true" geconfigureerd is.
void LilygoT547Display::full_clear() {
  epd_poweron();
  epd_fullclear(&hl, this->temperature_);
  epd_poweroff();
}

void LilygoT547Display::flush_screen_changes() {
  epd_poweron();
  err = epd_hl_update_screen(&hl, MODE_GC16, this->temperature_);
  if (err != EPD_DRAW_SUCCESS) {
    ESP_LOGE(TAG, "epd_hl_update_screen failed with error %d", (int) err);
  } else {
    ESP_LOGI(TAG, "Screen updated at %u C", (unsigned) this->temperature_);
  }
  // Het paneel heeft na het laatste waveform-frame nog even spanning nodig,
  // anders hardt het beeld niet uit en blijft het scherm vaag of leeg.
  delay(this->power_off_delay_enabled_ ? 700 : 250);
  epd_poweroff();
}

void LilygoT547Display::set_all_white() { epd_hl_set_all_white(&hl); }
void LilygoT547Display::poweron() { epd_poweron(); }
void LilygoT547Display::poweroff() { epd_poweroff(); }

void LilygoT547Display::on_shutdown() {
  ESP_LOGI(TAG, "Shutting down Lilygo T5-4.7 screen");
  epd_poweroff();
  epd_deinit();
}

// epdiy: 255 = wit, 0 = zwart (epd_hl_set_all_white doet memset 0xFF).
// De upstream-versie draaide dit om, waardoor zwarte tekst als wit werd
// weggeschreven: onzichtbaar, en epd_hl_update_screen zag geen verschil met
// het vorige beeld en stuurde dus helemaal niets naar het paneel.
void HOT LilygoT547Display::draw_absolute_pixel_internal(int x, int y, Color color) {
  int lum = (0.2126 * color.red) + (0.7152 * color.green) + (0.0722 * color.blue);
  if (lum < 0) {
    lum = 0;
  }
  if (lum > 255) {
    lum = 255;
  }
  epd_draw_pixel(x, y, (uint8_t) lum, fb);
}

}  // namespace lilygo_t5_47_display
}  // namespace esphome
