#include "ledController.h"

#include <linux/init.h>
#include <linux/module.h>
#include <linux/kernel.h>
#include <linux/gpio.h>
#include <linux/uaccess.h>

static int DevBusy = 0;
static int MajorNum = 100;
static struct class* ClassName = NULL;
static struct device* DeviceName = NULL;

static unsigned int led_gpios[2] = { 0, 0 };
module_param_array(led_gpios, uint, NULL, S_IRUGO);
MODULE_PARM_DESC(led_gpios, "GPIOs of the LEDs");

gpio_pin pins;

static int device_open(struct inode *inode, struct file *file) {
    printk(KERN_INFO "ledController: device_open(%p)\n", file);

    if (DevBusy)
        return -EBUSY;

    DevBusy++;
    try_module_get(THIS_MODULE);
    return 0;
}


static int device_release(struct inode *inode, struct file *file) {
    printk(KERN_INFO "ledController: device_release(%p)\n", file);
    DevBusy--;

    module_put(THIS_MODULE);
    return 0;
}


static int      device_ioctl(struct file *file, unsigned int cmd, unsigned long arg) {
    int ret_ignore;
    ret_ignore = 0;
    printk(KERN_DEBUG "ledController: Device IOCTL invoked : 0x%x - %u\n", cmd, cmd);

    switch (cmd) {
    case IOCTL_LEDCONTROLLER_GPIO_READ:
        memset(&pins, 0, sizeof(pins));
        ret_ignore = copy_from_user(&pins, (gpio_pin *)arg, sizeof(gpio_pin));
        pins.value = gpio_get_value(pins.pin);
        ret_ignore = copy_to_user((void *)arg, &pins, sizeof(gpio_pin));
        printk(KERN_INFO "ledController: IOCTL_LEDCONTROLLER_GPIO_READ");
        break;
    case IOCTL_LEDCONTROLLER_GPIO_WRITE:
        ret_ignore = copy_from_user(&pins, (gpio_pin *)arg, sizeof(gpio_pin));
        gpio_set_value(pins.pin, pins.value);
        printk(KERN_INFO "ledController: IOCTL_LEDCONTROLLER_GPIO_WRITE: pin:%u with value:%d\n", pins.pin, pins.value);
        break;
    case 0x5401:
    	printk(KERN_DEBUG "ledController: Ignore");
    	break;
    default:
        printk(KERN_DEBUG "ledController: Command format error\n");
    }

    return 0;
}


struct file_operations fops = {
    .unlocked_ioctl = device_ioctl,
    .open = device_open,
    .release = device_release,
};

static int __init ledController_init(void)
{

    int i, err, ret_val;
    i = 0;
    err = 0;
    ret_val = 0;

    for (i = 0; i < ARRAY_SIZE(led_gpios); i++) {
        if (led_gpios[i] == 0) {
            printk(KERN_ERR "ledController: LED not assigned");
            return -EINVAL;
        }

        err = gpio_request(led_gpios[i], "led");

        if (err) {
            printk(KERN_ERR "ledController: failed to request GPIO%d for LED\n", led_gpios[i]);
            return err;
        }

        err = gpio_direction_output(led_gpios[i], LED_OFF);
        if (err) {
            printk(KERN_ERR "ledController: failed to set direction for GPIO%d\n", led_gpios[i]);
            gpio_free(led_gpios[i]);
            return err;
        }

        gpio_direction_output(led_gpios[i], 0);
        gpio_export(led_gpios[i], false);

    }

    printk(KERN_INFO "ledController: Initializing the ledController\n");
    MajorNum = register_chrdev(0, DEVICE_NAME, &fops);
    if (MajorNum < 0) {
        for (i = 0; i < ARRAY_SIZE(led_gpios); i++) {
            gpio_unexport(led_gpios[i]);
            gpio_free(led_gpios[i]);
        }
        printk(KERN_ALERT "ledController: failed to register a major number\n");
        return MajorNum;
    }
    printk(KERN_INFO "ledController: registered with major number %d\n", MajorNum);

    ClassName = class_create(THIS_MODULE, CLASS_NAME);
    if (IS_ERR(ClassName)) {
        for (i = 0; i < ARRAY_SIZE(led_gpios); i++) {
            gpio_unexport(led_gpios[i]);
            gpio_free(led_gpios[i]);
        }
        unregister_chrdev(MajorNum, DEVICE_NAME);
        printk(KERN_ALERT "ledController: Failed to register device class\n");
        return PTR_ERR(ClassName);
    }
    printk(KERN_INFO "ledController: device class registered\n");

    DeviceName = device_create(ClassName, NULL, MKDEV(MajorNum, 0), NULL, DEVICE_NAME);
    if (IS_ERR(DeviceName)) {
        for (i = 0; i < ARRAY_SIZE(led_gpios); i++) {
            gpio_unexport(led_gpios[i]);
            gpio_free(led_gpios[i]);
        }
        class_destroy(ClassName);
        unregister_chrdev(MajorNum, DEVICE_NAME);
        printk(KERN_ALERT "ledController: Failed to create the device\n");
        return PTR_ERR(DeviceName);
    }
    printk(KERN_INFO "ledController: device class created\n");

    printk(KERN_INFO "ledController loaded\n");
    return 0;
}


static void __exit ledController_exit(void)
{
    int i;
    i = 0;
    device_destroy(ClassName, MKDEV(MajorNum, 0));
    class_unregister(ClassName);
    class_destroy(ClassName);
    unregister_chrdev(MajorNum, DEVICE_NAME);
    printk(KERN_INFO "ledController: device and class removed\n");

    for (i = 0; i < ARRAY_SIZE(led_gpios); i++) {
        gpio_set_value(led_gpios[i], LED_OFF);
        gpio_unexport(led_gpios[i]);
        gpio_free(led_gpios[i]);
    }
    printk(KERN_INFO "ledController successfully unloaded\n");
}


module_init(ledController_init);
module_exit(ledController_exit);

MODULE_LICENSE("GPL");
MODULE_AUTHOR("Lukas Smith");
MODULE_DESCRIPTION("A LKM to control multiple LEDs");
MODULE_VERSION("0.1");
