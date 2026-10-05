######################################
#
# nhe-can-abyss
#
# Can-Abyss Delay by New Horizon Electronics
# https://github.com/Kiwooky/NHE-Can-Abyss
#
# This file is the plugin's package for mod-plugin-builder
# (plugins/package/nhe-can-abyss/nhe-can-abyss.mk). The same file can be
# uploaded to https://builder.mod.audio/buildroot to get an install link.
#
# Set NHE_CAN_ABYSS_VERSION to the full hash of the commit to build.
#
######################################

NHE_CAN_ABYSS_VERSION = COMMIT_HASH_HERE
NHE_CAN_ABYSS_SITE = $(call github,Kiwooky,NHE-Can-Abyss,$(NHE_CAN_ABYSS_VERSION))
NHE_CAN_ABYSS_BUNDLES = nhe-can-abyss.lv2

NHE_CAN_ABYSS_TARGET_MAKE = $(TARGET_MAKE_ENV) $(TARGET_CONFIGURE_OPTS) $(MAKE) NOOPT=true -C $(@D)

define NHE_CAN_ABYSS_BUILD_CMDS
	$(NHE_CAN_ABYSS_TARGET_MAKE)
endef

define NHE_CAN_ABYSS_INSTALL_TARGET_CMDS
	$(NHE_CAN_ABYSS_TARGET_MAKE) install DESTDIR=$(TARGET_DIR) PREFIX=/usr
endef

$(eval $(generic-package))
