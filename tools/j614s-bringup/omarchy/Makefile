CC ?= cc
CFLAGS ?= -O2 -std=c11 -Wall -Wextra -Werror

.PHONY: all check clean
all: evidence/render_probe

evidence/render_probe: render_probe.c
	mkdir -p evidence
	$(CC) $(CFLAGS) $< -o $@ $$(pkg-config --cflags --libs egl glesv2)

check: all
	python3 -m unittest discover -s . -v
	@if ./evidence/render_probe /dev/dri/renderD9999; then echo "unexpected missing-node success"; exit 1; fi

clean:
	rm -f evidence/render_probe
