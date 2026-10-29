/* Blank only the built-in panel's colour lookup table; preserve it exactly.
 * VNC reads the framebuffer before this hardware colour transformation. */
#include <X11/Xlib.h>
#include <X11/extensions/Xrandr.h>
#include <sys/stat.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#ifndef XPS_PANEL_OUTPUT
#error "Build with an explicit XPS_PANEL_OUTPUT string"
#endif

struct header { uint32_t magic, size; uint64_t crtc; };

static void fail(const char *message) {
    fprintf(stderr, "XPS panel: %s\n", message);
    exit(1);
}

int main(int argc, char **argv) {
    if (argc != 3 || (strcmp(argv[1], "save") && strcmp(argv[1], "blank") && strcmp(argv[1], "restore")))
        fail("use save, blank or restore with a private state file");
    Display *d = XOpenDisplay(NULL);
    if (!d) fail("cannot open the current X display");
    XRRScreenResources *res = XRRGetScreenResourcesCurrent(d, DefaultRootWindow(d));
    if (!res) fail("cannot read display resources");
    RRCrtc crtc = None;
    for (int i = 0; i < res->noutput; ++i) {
        XRROutputInfo *out = XRRGetOutputInfo(d, res, res->outputs[i]);
        if (out && out->connection == RR_Connected && out->crtc &&
            out->nameLen == (int)strlen(XPS_PANEL_OUTPUT) &&
            !memcmp(out->name, XPS_PANEL_OUTPUT, out->nameLen)) {
            if (crtc) fail("more than one active built-in panel");
            crtc = out->crtc;
        }
        if (out) XRRFreeOutputInfo(out);
    }
    XRRFreeScreenResources(res);
    if (!crtc) fail("no active configured built-in panel");
    XRRCrtcGamma *current = XRRGetCrtcGamma(d, crtc);
    if (!current || current->size < 1 || current->size > 65536) fail("invalid panel lookup table");
    struct header h = {0x58504731, (uint32_t)current->size, (uint64_t)crtc};
    if (!strcmp(argv[1], "save")) {
        int fd = open(argv[2], O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW, 0600);
        if (fd < 0) fail("cannot create private recovery file");
        FILE *f = fdopen(fd, "wb");
        if (!f || fwrite(&h, sizeof(h), 1, f) != 1 ||
            fwrite(current->red, 2, h.size, f) != h.size ||
            fwrite(current->green, 2, h.size, f) != h.size ||
            fwrite(current->blue, 2, h.size, f) != h.size || fclose(f))
            fail("cannot save the original lookup table");
    } else {
        int fd = open(argv[2], O_RDONLY | O_NOFOLLOW);
        struct stat st;
        struct header saved;
        if (fd < 0 || fstat(fd, &st) || !S_ISREG(st.st_mode) || st.st_uid != getuid() || (st.st_mode & 077))
            fail("unexpected recovery file ownership or permissions");
        FILE *f = fdopen(fd, "rb");
        if (!f || fread(&saved, sizeof(saved), 1, f) != 1 || saved.magic != h.magic ||
            saved.size != h.size || saved.crtc != h.crtc || st.st_size != (off_t)(sizeof(saved) + 6 * saved.size))
            fail("recovery file does not match the current panel");
        XRRCrtcGamma *next = XRRAllocGamma(saved.size);
        if (!next || fread(next->red, 2, saved.size, f) != saved.size ||
            fread(next->green, 2, saved.size, f) != saved.size ||
            fread(next->blue, 2, saved.size, f) != saved.size || fclose(f))
            fail("cannot read the original lookup table");
        int zero = 1;
        for (int i = 0; i < current->size; ++i)
            if (current->red[i] || current->green[i] || current->blue[i]) zero = 0;
        if (!strcmp(argv[1], "blank")) {
            memset(next->red, 0, 2 * saved.size);
            memset(next->green, 0, 2 * saved.size);
            memset(next->blue, 0, 2 * saved.size);
        }
        /* Preserve any colour adjustment the user made after our blanking. */
        if (!strcmp(argv[1], "blank") || zero) {
            XRRSetCrtcGamma(d, crtc, next);
            XSync(d, False);
        }
        XRRFreeGamma(next);
    }
    XRRFreeGamma(current);
    XCloseDisplay(d);
    return 0;
}
