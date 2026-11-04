######################################
#
# nhe-can-abyss-stereo
#
# Can-Abyss Delay Stereo by New Horizon Electronics
# https://github.com/Kiwooky/NHE-Can-Abyss-Stereo
#
# This file is the plugin's package for mod-plugin-builder
# (plugins/package/nhe-can-abyss-stereo/nhe-can-abyss-stereo.mk). The same file can be
# uploaded to https://builder.mod.audio/buildroot to get an install link
# (only while the repo it points at is public).
#
# Set NHE_CAN_ABYSS_STEREO_VERSION to the full hash of the commit to build.
#
######################################

NHE_CAN_ABYSS_STEREO_VERSION = 0000000000000000000000000000000000000000
NHE_CAN_ABYSS_STEREO_SITE = https://github.com/Kiwooky/NHE-Can-Abyss-Stereo.git
NHE_CAN_ABYSS_STEREO_SITE_METHOD = git
NHE_CAN_ABYSS_STEREO_GIT_SUBMODULES = y
# fetch git submodules (DPF), as MOD's own packages do (mod-plugin-builder)
NHE_CAN_ABYSS_STEREO_PRE_DOWNLOAD_HOOKS += MOD_PLUGIN_BUILDER_DOWNLOAD_WITH_SUBMODULES

NHE_CAN_ABYSS_STEREO_BUNDLES = nhe-can-abyss-stereo.lv2

NHE_CAN_ABYSS_STEREO_TARGET_MAKE = $(TARGET_MAKE_ENV) $(TARGET_CONFIGURE_OPTS) $(MAKE) NOOPT=true NAME=nhe-can-abyss-stereo -C $(@D)

define NHE_CAN_ABYSS_STEREO_BUILD_CMDS
	$(NHE_CAN_ABYSS_STEREO_TARGET_MAKE)
endef

define NHE_CAN_ABYSS_STEREO_INSTALL_TARGET_CMDS
	$(NHE_CAN_ABYSS_STEREO_TARGET_MAKE) install DESTDIR=$(TARGET_DIR) PREFIX=/usr
endef

$(eval $(generic-package))
