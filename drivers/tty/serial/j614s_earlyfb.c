// SPDX-License-Identifier: GPL-2.0-only
/* [DEBUG-J614S-ENTRY] Private diagnostic for one exact captured framebuffer. */
#include <linux/console.h>
#include <linux/font.h>
#include <linux/init.h>
#include <linux/io.h>
#include <linux/serial_core.h>
#include <asm/early_ioremap.h>

#define J614S_FB_BASE 1124735713280ULL
#define J614S_FB_STRIDE 12096
#define J614S_FB_HEIGHT 1964
#define J614S_TEXT_TOP 256
#define J614S_COLS 160
static void __iomem *j614s_fb;
static char j614s_line[J614S_COLS];
static unsigned int j614s_x, j614s_y;

static void __ref j614s_draw_line(void)
{
 unsigned int row, col, bit, repeat;
 for (row = 0; row < 16; row++) {
  unsigned long offset = (J614S_TEXT_TOP + j614s_y * 32 + row * 2) * J614S_FB_STRIDE;
  void __iomem *mapped = j614s_fb ? j614s_fb + offset : early_ioremap(J614S_FB_BASE + offset, 2 * J614S_FB_STRIDE);
  if (!mapped)
   return;
  for (col = 0; col < J614S_COLS; col++) {
   unsigned char ch = col < j614s_x ? j614s_line[col] : ' ';
   unsigned char glyph = ((const unsigned char *)font_vga_8x16.data)[ch * 16 + row];
   for (bit = 0; bit < 8; bit++) {
    u32 colour = glyph & (0x80 >> bit) ? 0x3fffffff : 0;
    for (repeat = 0; repeat < 2; repeat++) {
     unsigned long x = (col * 16 + bit * 2) * 4;
     writel_relaxed(colour, mapped + repeat * J614S_FB_STRIDE + x);
     writel_relaxed(colour, mapped + repeat * J614S_FB_STRIDE + x + 4);
    }
   }
  }
  if (!j614s_fb)
   early_iounmap(mapped, 2 * J614S_FB_STRIDE);
 }
 wmb();
}

static void __ref j614s_fb_write(struct console *con, const char *text, unsigned int count)
{
 while (count--) {
  char ch = *text++;
  if (ch == '\r') {
   j614s_x = 0;
   continue;
  }
  if (ch != '\n')
   j614s_line[j614s_x++] = ch;
  if (ch == '\n' || j614s_x == J614S_COLS) {
   j614s_draw_line();
   j614s_x = 0;
   j614s_y = (j614s_y + 1) % ((J614S_FB_HEIGHT - J614S_TEXT_TOP) / 32);
  }
 }
 if (j614s_x)
  j614s_draw_line();
}

static int __init j614s_fb_setup(struct earlycon_device *device, const char *options)
{
 device->con->write = j614s_fb_write;
 return 0;
}
EARLYCON_DECLARE(j614sfb, j614s_fb_setup);

static int __init j614s_fb_remap(void)
{
 j614s_fb = ioremap_wc(J614S_FB_BASE, J614S_FB_STRIDE * J614S_FB_HEIGHT);
 return j614s_fb ? 0 : -ENOMEM;
}
early_initcall(j614s_fb_remap);
