#!/usr/bin/make -f
# Can-Abyss Delay - top-level build
#
#   make                      build bin/nhe-can-abyss.lv2 (DSP + TTL + pedal face)
#   make NAME=<bundle name>   build another plugin in this repo (plugins/<name without nhe->)
#   make install DESTDIR=...  install into $(DESTDIR)$(PREFIX)/lib/lv2
#   make clean
#
# Cross builds take the usual CC/CXX/CXXFLAGS from the environment, which is
# what mod-plugin-builder and builder.mod.audio pass in.

PREFIX  ?= /usr/local
NAME    ?= nhe-can-abyss
BUNDLE  := $(NAME).lv2
PLUGDIR := plugins/$(patsubst nhe-%,%,$(NAME))

all: plugin bundle

plugin:
	$(MAKE) -C $(PLUGDIR)

bundle: plugin
	cp -r bundle/$(BUNDLE)/. bin/$(BUNDLE)/

install: all
	install -d $(DESTDIR)$(PREFIX)/lib/lv2/$(BUNDLE)
	cp -r bin/$(BUNDLE)/. $(DESTDIR)$(PREFIX)/lib/lv2/$(BUNDLE)/

clean:
	$(MAKE) -C $(PLUGDIR) clean
	rm -rf bin build

.PHONY: all plugin bundle install clean
