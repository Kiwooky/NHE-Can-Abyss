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

NHE_CAN_ABYSS_VERSION = c56ddb59054513fcc94d3f8c16a8b13924c2acd4
NHE_CAN_ABYSS_SITE = https://github.com/Kiwooky/NHE-Can-Abyss.git
NHE_CAN_ABYSS_SITE_METHOD = git
NHE_CAN_ABYSS_GIT_SUBMODULES = y
# fetch git submodules (DPF), as MOD's own packages do (mod-plugin-builder)
NHE_CAN_ABYSS_PRE_DOWNLOAD_HOOKS += MOD_PLUGIN_BUILDER_DOWNLOAD_WITH_SUBMODULES

NHE_CAN_ABYSS_BUNDLES = nhe-can-abyss.lv2

NHE_CAN_ABYSS_TARGET_MAKE = $(TARGET_MAKE_ENV) $(TARGET_CONFIGURE_OPTS) $(MAKE) NOOPT=true -C $(@D)

define NHE_CAN_ABYSS_BUILD_CMDS
	$(NHE_CAN_ABYSS_TARGET_MAKE)
endef

define NHE_CAN_ABYSS_INSTALL_TARGET_CMDS
	$(NHE_CAN_ABYSS_TARGET_MAKE) install DESTDIR=$(TARGET_DIR) PREFIX=/usr
endef

$(eval $(generic-package))
