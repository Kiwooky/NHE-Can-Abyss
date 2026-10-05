#!/usr/bin/make -f
# Can-Abyss Delay - top-level build
#
#   make                      build bin/nhe-can-abyss.lv2 (DSP + TTL + pedal face)
#   make install DESTDIR=...  install into $(DESTDIR)$(PREFIX)/lib/lv2
#   make clean
#
# Cross builds take the usual CC/CXX/CXXFLAGS from the environment, which is
# what mod-plugin-builder and builder.mod.audio pass in.

PREFIX  ?= /usr/local
BUNDLE  := nhe-can-abyss.lv2

all: plugin bundle

plugin:
	$(MAKE) -C plugins/can-abyss

bundle: plugin
	cp -r bundle/$(BUNDLE)/. bin/$(BUNDLE)/

install: all
	install -d $(DESTDIR)$(PREFIX)/lib/lv2/$(BUNDLE)
	cp -r bin/$(BUNDLE)/. $(DESTDIR)$(PREFIX)/lib/lv2/$(BUNDLE)/

clean:
	$(MAKE) -C plugins/can-abyss clean
	rm -rf bin build

.PHONY: all plugin bundle install clean
