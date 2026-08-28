#pragma once
#include "esphome/core/component.h"

#include "esphome/components/display/display_buffer.h"
#include "esphome/components/display/display_color_utils.h"
#include "esphome/core/hal.h"
#include "esphome/core/version.h"

// De publieke epdiy-header heet tegenwoordig epdiy.h. epd_driver.h bestaat
// niet meer; epdiy.h include't zelf epd_highlevel.h, epd_board.h enz.
#ifndef EPD_DRIVER
#define EPD_DRIVER
#include "epdiy.h"
#endif

namespace esphome {
namespace lilygo_t5_47_display {

// LilyGo-EPD47
// Erft alleen van DisplayBuffer. DisplayBuffer -> Display -> PollingComponent,
// dus ook van PollingComponent erven maakt de basisklasse ambigu.
class LilygoT547Display : public display::DisplayBuffer {
 protected:
  EpdiyHighlevelState hl;
  uint8_t *fb;
  enum EpdDrawError err;

 public:
  float get_setup_priority() const override;

  void set_clear_screen(bool clear);
  void set_landscape(bool landscape);
  void set_power_off_delay_enabled(bool power_off_delay_enabled);
  void set_temperature(uint32_t temperature);

  int get_width_internal();

  int get_height_internal();

  void setup() override;

  void update() override;

  void clear() override;
  void full_clear();
  void flush_screen_changes();
  void set_all_white();
  void poweron();
  void poweroff();
  void on_shutdown() override;

#if ESPHOME_VERSION_CODE >= VERSION_CODE(2022,6,0)
  display::DisplayType get_display_type() override { return display::DisplayType::DISPLAY_TYPE_GRAYSCALE; }
#endif

 protected:
  void HOT draw_absolute_pixel_internal(int x, int y, Color color) override;

  bool clear_;
  bool init_clear_executed_ = false;
  // uint32_t, niet bool: als bool werd set_temperature(23) stilletjes 1.
  uint32_t temperature_;
  bool power_off_delay_enabled_;
  bool landscape_;
};

}  // namespace lilygo_t5_47_display
}  // namespace esphome
