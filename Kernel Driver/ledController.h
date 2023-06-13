#ifndef LEDCONTROLLER_H
#define LEDCONTROLLER_H

#include <linux/ioctl.h>

typedef struct gpio_pin {
	unsigned int pin;
	int value;
} gpio_pin;

#define IOCTL_LEDCONTROLLER_GPIO_READ 0x65
#define IOCTL_LEDCONTROLLER_GPIO_WRITE 0x66

#define LED_ON 1
#define LED_OFF 0

#define  DEVICE_NAME "ledControllerDev"
#define  CLASS_NAME  "ledControllerCLS"

#endif
