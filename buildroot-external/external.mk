# Home Pi adds no Buildroot packages; everything lands via the rootfs overlay
# and board/homepi/post-build.sh. Kept so package/homepi-* can be added later.
include $(sort $(wildcard $(BR2_EXTERNAL_HOMEPI_PATH)/package/*/*.mk))
