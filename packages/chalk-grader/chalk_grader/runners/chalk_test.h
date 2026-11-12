/*
 * chalk_test.h: a small C test framework for the c-make profile of chalk.
 *
 * Include it in exactly one source file, which becomes the test program:
 *
 *     #include "chalk_test.h"
 *     #include "calc.h"
 *
 *     TEST(add) { CHECK_EQ(add(1, 2), 3); }
 *     TEST(sub) { CHECK(sub(3, 2) == 1); }
 *
 * The header defines main(). Each test runs in its own process, so a crash
 * or an endless loop fails only that test. Results go to stdout and, when
 * the CHALK_RESULT variable is set, to a JUnit report in that file.
 *
 * Environment: CHALK_TEST_TIMEOUT sets the timeout of each test in seconds
 * (default 5).
 */
#ifndef CHALK_TEST_H
#define CHALK_TEST_H

#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/wait.h>
#include <unistd.h>

#define CHALK_MAX_TESTS 1024
#define CHALK_MAX_MESSAGE 512
#define CHALK_FAILED 99

struct chalk_test {
    const char *name;
    void (*fn)(void);
};

static struct chalk_test chalk_tests[CHALK_MAX_TESTS];
static int chalk_test_count;
static int chalk_message_fd = -1;

#define TEST(id)                                                               \
    static void chalk_test_##id(void);                                         \
    __attribute__((constructor)) static void chalk_register_##id(void) {       \
        if (chalk_test_count < CHALK_MAX_TESTS) {                              \
            chalk_tests[chalk_test_count].name = #id;                          \
            chalk_tests[chalk_test_count].fn = chalk_test_##id;                \
            chalk_test_count++;                                                \
        }                                                                      \
    }                                                                          \
    static void chalk_test_##id(void)

static void chalk_fail(const char *file, int line, const char *fmt, ...)
    __attribute__((noreturn, format(printf, 3, 4)));

#include <stdarg.h>

static void chalk_fail(const char *file, int line, const char *fmt, ...) {
    char message[CHALK_MAX_MESSAGE];
    int n = snprintf(message, sizeof message, "%s:%d: ", file, line);
    va_list args;
    va_start(args, fmt);
    vsnprintf(message + n, sizeof message - n, fmt, args);
    va_end(args);
    if (chalk_message_fd >= 0) {
        ssize_t written = write(chalk_message_fd, message, strlen(message));
        (void)written;
    }
    _exit(CHALK_FAILED);
}

#define CHECK(cond)                                                            \
    do {                                                                       \
        if (!(cond)) chalk_fail(__FILE__, __LINE__, "CHECK(%s) failed", #cond); \
    } while (0)

#define CHECK_EQ(a, b)                                                         \
    do {                                                                       \
        long long chalk_a = (long long)(a), chalk_b = (long long)(b);          \
        if (chalk_a != chalk_b)                                                \
            chalk_fail(__FILE__, __LINE__, "%s == %s: %lld != %lld", #a, #b,   \
                       chalk_a, chalk_b);                                      \
    } while (0)

#define CHECK_STREQ(a, b)                                                      \
    do {                                                                       \
        const char *chalk_a = (a), *chalk_b = (b);                             \
        if (!chalk_a || !chalk_b || strcmp(chalk_a, chalk_b) != 0)             \
            chalk_fail(__FILE__, __LINE__, "%s == %s: \"%.100s\" != \"%.100s\"", \
                       #a, #b, chalk_a ? chalk_a : "(null)",                   \
                       chalk_b ? chalk_b : "(null)");                          \
    } while (0)

#define CHECK_NEAR(a, b, eps)                                                  \
    do {                                                                       \
        double chalk_a = (a), chalk_b = (b), chalk_d = chalk_a - chalk_b;      \
        if (chalk_d < -(eps) || chalk_d > (eps))                               \
            chalk_fail(__FILE__, __LINE__, "%s == %s: %g != %g", #a, #b,       \
                       chalk_a, chalk_b);                                      \
    } while (0)

static void chalk_xml(FILE *out, const char *text) {
    for (; *text; text++) {
        switch (*text) {
            case '&': fputs("&amp;", out); break;
            case '<': fputs("&lt;", out); break;
            case '>': fputs("&gt;", out); break;
            case '"': fputs("&quot;", out); break;
            default:
                if ((unsigned char)*text >= 0x20 || *text == '\n' || *text == '\t')
                    fputc(*text, out);
        }
    }
}

/* Run one test in a child process; return NULL when it passes or the reason
 * it failed in message. */
static const char *chalk_run(const struct chalk_test *test, int timeout,
                             char *message, size_t size) {
    int fds[2];
    if (pipe(fds) != 0) return "cannot create a pipe";
    fflush(NULL);
    pid_t pid = fork();
    if (pid < 0) return "cannot fork";
    if (pid == 0) {
        close(fds[0]);
        chalk_message_fd = fds[1];
        alarm((unsigned)timeout);
        test->fn();
        _exit(0);
    }
    close(fds[1]);
    size_t used = 0;
    ssize_t n;
    while (used < size - 1 && (n = read(fds[0], message + used, size - 1 - used)) > 0)
        used += (size_t)n;
    message[used] = '\0';
    close(fds[0]);

    int status;
    while (waitpid(pid, &status, 0) < 0) {}
    if (WIFEXITED(status)) {
        int code = WEXITSTATUS(status);
        if (code == 0) return NULL;
        if (code != CHALK_FAILED || used == 0)
            snprintf(message, size, "exited with code %d", code);
        return message;
    }
    if (WIFSIGNALED(status)) {
        int sig = WTERMSIG(status);
        if (sig == SIGALRM)
            snprintf(message, size, "timed out after %ds", timeout);
        else
            snprintf(message, size, "crashed with signal %d (%s)", sig, strsignal(sig));
        return message;
    }
    return "stopped";
}

int main(void) {
    const char *env = getenv("CHALK_TEST_TIMEOUT");
    int timeout = env && atoi(env) > 0 ? atoi(env) : 5;
    static char messages[CHALK_MAX_TESTS][CHALK_MAX_MESSAGE];
    const char *errors[CHALK_MAX_TESTS];
    int passed = 0;

    for (int i = 0; i < chalk_test_count; i++) {
        errors[i] = chalk_run(&chalk_tests[i], timeout, messages[i], CHALK_MAX_MESSAGE);
        if (errors[i] == NULL) passed++;
        printf("%s %s%s%s\n", errors[i] ? "FAIL" : "ok", chalk_tests[i].name,
               errors[i] ? ": " : "", errors[i] ? errors[i] : "");
    }
    printf("%d/%d tests passed\n", passed, chalk_test_count);

    const char *path = getenv("CHALK_RESULT");
    if (path != NULL && *path) {
        FILE *out = fopen(path, "w");
        if (out == NULL) {
            perror(path);
            return 2;
        }
        fprintf(out, "<?xml version=\"1.0\"?>\n<testsuites><testsuite name=\"c\" tests=\"%d\">",
                chalk_test_count);
        for (int i = 0; i < chalk_test_count; i++) {
            fprintf(out, "<testcase classname=\"c\" name=\"");
            chalk_xml(out, chalk_tests[i].name);
            if (errors[i] == NULL) {
                fputs("\"/>", out);
            } else {
                fputs("\"><failure message=\"", out);
                chalk_xml(out, errors[i]);
                fputs("\"/></testcase>", out);
            }
        }
        fputs("</testsuite></testsuites>\n", out);
        fclose(out);
    }
    return passed == chalk_test_count ? 0 : 1;
}

#endif
