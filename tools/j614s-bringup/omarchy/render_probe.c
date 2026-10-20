/* Bind an EGL device to one DRM render node, clear a pbuffer and read it back.
 * No DRM modeset, display selection, boot changes or software fallback. */
#include <EGL/egl.h>
#include <EGL/eglext.h>
#include <GLES2/gl2.h>
#include <stdio.h>
#include <string.h>

static void string_json(const char *s)
{
    putchar('"');
    for (; *s; s++) {
        unsigned char c = (unsigned char)*s;
        if (c == '"' || c == '\\') printf("\\%c", c);
        else if (c < 32) printf("\\u%04x", c);
        else putchar(c);
    }
    putchar('"');
}

int main(int argc, char **argv)
{
    PFNEGLQUERYDEVICESEXTPROC query = (PFNEGLQUERYDEVICESEXTPROC)eglGetProcAddress("eglQueryDevicesEXT");
    PFNEGLQUERYDEVICESTRINGEXTPROC name = (PFNEGLQUERYDEVICESTRINGEXTPROC)eglGetProcAddress("eglQueryDeviceStringEXT");
    PFNEGLGETPLATFORMDISPLAYEXTPROC display = (PFNEGLGETPLATFORMDISPLAYEXTPROC)eglGetProcAddress("eglGetPlatformDisplayEXT");
    EGLDeviceEXT devices[64];
    EGLint count = 0;
    EGLDisplay dpy = EGL_NO_DISPLAY;
    if (argc != 2 || !query || !name || !display || !query(64, devices, &count)) {
        fprintf(stderr, "EGL device enumeration unavailable\n");
        return 1;
    }
    if (count < 0 || count > 64) {
        fprintf(stderr, "EGL device enumeration count outside array bounds\n");
        return 1;
    }
    for (EGLint i = 0; i < count; i++) {
        const char *node = name(devices[i], EGL_DRM_RENDER_NODE_FILE_EXT);
        if (node && strcmp(node, argv[1]) == 0) {
            dpy = display(EGL_PLATFORM_DEVICE_EXT, devices[i], NULL);
            break;
        }
    }
    EGLint major, minor, configs;
    EGLConfig config;
    const EGLint attributes[] = {EGL_SURFACE_TYPE, EGL_PBUFFER_BIT,
        EGL_RENDERABLE_TYPE, EGL_OPENGL_ES2_BIT, EGL_RED_SIZE, 8,
        EGL_GREEN_SIZE, 8, EGL_BLUE_SIZE, 8, EGL_NONE};
    const EGLint surface_attributes[] = {EGL_WIDTH, 4, EGL_HEIGHT, 4, EGL_NONE};
    const EGLint context_attributes[] = {EGL_CONTEXT_CLIENT_VERSION, 2, EGL_NONE};
    if (dpy == EGL_NO_DISPLAY || !eglInitialize(dpy, &major, &minor)
        || !eglBindAPI(EGL_OPENGL_ES_API)
        || !eglChooseConfig(dpy, attributes, &config, 1, &configs) || configs != 1) {
        fprintf(stderr, "No EGL pbuffer config on requested DRM node: %#x\n", eglGetError());
        return 1;
    }
    EGLSurface surface = eglCreatePbufferSurface(dpy, config, surface_attributes);
    EGLContext context = eglCreateContext(dpy, config, EGL_NO_CONTEXT, context_attributes);
    if (surface == EGL_NO_SURFACE || context == EGL_NO_CONTEXT
        || !eglMakeCurrent(dpy, surface, surface, context)) {
        fprintf(stderr, "EGL context creation failed: %#x\n", eglGetError());
        eglTerminate(dpy);
        return 1;
    }
    const char *renderer = (const char *)glGetString(GL_RENDERER);
    const char *vendor = (const char *)glGetString(GL_VENDOR);
    unsigned char pixels[4 * 4 * 4] = {0};
    glClearColor(0.0f, 1.0f, 0.0f, 1.0f);
    glClear(GL_COLOR_BUFFER_BIT);
    glReadPixels(0, 0, 4, 4, GL_RGBA, GL_UNSIGNED_BYTE, pixels);
    int good = glGetError() == GL_NO_ERROR && renderer && vendor;
    for (unsigned i = 0; i < sizeof(pixels); i += 4)
        good = good && pixels[i] == 0 && pixels[i + 1] == 255 && pixels[i + 2] == 0;
    if (good) {
        printf("{\"node\":"); string_json(argv[1]);
        printf(",\"renderer\":"); string_json(renderer);
        printf(",\"vendor\":"); string_json(vendor);
        printf(",\"pixel_test\":true}\n");
    } else fprintf(stderr, "EGL pixel readback failed\n");
    eglMakeCurrent(dpy, EGL_NO_SURFACE, EGL_NO_SURFACE, EGL_NO_CONTEXT);
    eglDestroyContext(dpy, context);
    eglDestroySurface(dpy, surface);
    eglTerminate(dpy);
    return good ? 0 : 1;
}
