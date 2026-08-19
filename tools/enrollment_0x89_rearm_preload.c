/*
 * Repository-local, experimental enrollment interposer.
 *
 * The only interposed driver function is cv_fingerprint_update_enrollment().
 * The default legacy-repeat policy makes exactly one additional call after
 * 0x59, preserving the original diagnostic behavior.  The explicitly
 * selected fresh-stop-before-commit policies never repeat 0x59 and block a
 * native nonzero completion before the outer state machine can enter generic
 * commit.  The fresh-rearm variant additionally sends one target-local 0x8a
 * after each accepted incomplete update, with a four-update hard stop.
 *
 * A 0x89 result causes the existing target-local
 * cv_cmd_enrollment_started()/0x8a function to run before the original 0x89
 * is returned to the unchanged TOD retry callback.
 *
 * The proprietary TOD plugin is loaded with G_MODULE_BIND_LOCAL.  Therefore
 * RTLD_NEXT is intentionally never used.  Original symbols are resolved from
 * a verified RTLD_NOLOAD handle for the exact already-loaded target DSO.
 */

#define _GNU_SOURCE

#include <dlfcn.h>
#include <errno.h>
#include <limits.h>
#include <link.h>
#include <pthread.h>
#include <stdarg.h>
#include <stdatomic.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>

#define CV_STATUS_SUCCESS 0x00u
#define CV_STATUS_UPDATE_AGAIN_EXPERIMENT 0x59u
#define CV_STATUS_BAD_CAPTURE 0x89u
#define CV_STATUS_CAPTURE_FAILED 0xa4u
#define CV_STATUS_ENROLL_MORE 0x8fu
#define CV_STATUS_EXPERIMENT_FAILURE 0x100003u
#define CV2_TARGET_ENV "CV2_0X89_TARGET_PATH"
#define CV2_UPDATE_POLICY_ENV "CV2_ENROLLMENT_UPDATE_POLICY"
#define CV2_POLICY_LEGACY "legacy-repeat"
#define CV2_POLICY_FRESH "fresh-stop-before-commit"
#define CV2_POLICY_FRESH_REARM "fresh-rearm-stop-before-commit"
#define CV2_MAX_ACCEPTED_UPDATES 4u

typedef enum
{
  UPDATE_POLICY_LEGACY_REPEAT,
  UPDATE_POLICY_FRESH_STOP_BEFORE_COMMIT,
  UPDATE_POLICY_FRESH_REARM_STOP_BEFORE_COMMIT,
} UpdatePolicy;

typedef uint32_t (*cv_cmd_enrollment_started_fn) (void);
typedef uint32_t (*cv_fingerprint_update_enrollment_fn) (
  uint32_t handle,
  const void *enrollment_id,
  uint32_t auxiliary_input_size,
  const void *auxiliary_input,
  uint8_t *completion_out,
  void *enrollment_data_out,
  uint32_t *output_value_out);

typedef struct
{
  char path[PATH_MAX];
  dev_t device;
  ino_t inode;
} TargetIdentity;

typedef struct
{
  TargetIdentity expected;
  bool found;
} LoadedSearch;

typedef struct
{
  void *handle;
  cv_fingerprint_update_enrollment_fn update;
  cv_cmd_enrollment_started_fn enrollment_started;
  UpdatePolicy update_policy;
  bool ready;
  char failure[512];
} ResolverCache;

uint32_t cv_fingerprint_update_enrollment (uint32_t handle,
                                           const void *enrollment_id,
                                           uint32_t auxiliary_input_size,
                                           const void *auxiliary_input,
                                           uint8_t *completion_out,
                                           void *enrollment_data_out,
                                           uint32_t *output_value_out);

static pthread_once_t resolver_once = PTHREAD_ONCE_INIT;
static ResolverCache resolver;
static atomic_uint retry_attempt = ATOMIC_VAR_INIT (0);
static atomic_uint accepted_incomplete_count = ATOMIC_VAR_INIT (0);

static const char *
update_policy_name (UpdatePolicy policy)
{
  switch (policy)
    {
    case UPDATE_POLICY_LEGACY_REPEAT:
      return CV2_POLICY_LEGACY;
    case UPDATE_POLICY_FRESH_STOP_BEFORE_COMMIT:
      return CV2_POLICY_FRESH;
    case UPDATE_POLICY_FRESH_REARM_STOP_BEFORE_COMMIT:
      return CV2_POLICY_FRESH_REARM;
    }
  return "<invalid>";
}

static void
resolver_failure (const char *format, ...)
{
  va_list args;

  va_start (args, format);
  vsnprintf (resolver.failure, sizeof resolver.failure, format, args);
  va_end (args);
  fprintf (stderr,
           "[cv2-0x89-resolver] symbol resolution failed: %s\n",
           resolver.failure);
}

static bool
identity_from_path (const char *path, TargetIdentity *identity)
{
  struct stat metadata;

  if (path == NULL || path[0] == '\0')
    return false;
  if (realpath (path, identity->path) == NULL)
    return false;
  if (stat (identity->path, &metadata) != 0)
    return false;
  identity->device = metadata.st_dev;
  identity->inode = metadata.st_ino;
  return true;
}

static int
find_loaded_target (struct dl_phdr_info *info, size_t size, void *user_data)
{
  LoadedSearch *search = user_data;
  TargetIdentity candidate;

  (void) size;
  if (!identity_from_path (info->dlpi_name, &candidate))
    return 0;
  if (strcmp (candidate.path, search->expected.path) == 0 &&
      candidate.device == search->expected.device &&
      candidate.inode == search->expected.inode)
    {
      search->found = true;
      return 1;
    }
  return 0;
}

static bool
symbol_owned_by_target (void *address,
                        const char *name,
                        const TargetIdentity *target,
                        void *self_address)
{
  Dl_info owner;
  TargetIdentity owner_identity;

  if (address == NULL)
    {
      resolver_failure ("target symbol %s was not found", name);
      return false;
    }
  if (address == self_address)
    {
      resolver_failure (
        "target symbol %s resolved to the interposer wrapper; refusing recursion",
        name);
      return false;
    }
  memset (&owner, 0, sizeof owner);
  if (dladdr (address, &owner) == 0 || owner.dli_fname == NULL)
    {
      resolver_failure ("dladdr could not identify owner of %s", name);
      return false;
    }
  if (!identity_from_path (owner.dli_fname, &owner_identity))
    {
      resolver_failure ("could not canonicalize owner of %s: %s",
                        name,
                        owner.dli_fname);
      return false;
    }
  if (strcmp (owner_identity.path, target->path) != 0 ||
      owner_identity.device != target->device ||
      owner_identity.inode != target->inode)
    {
      resolver_failure ("symbol %s belongs to unexpected DSO %s",
                        name,
                        owner_identity.path);
      return false;
    }
  fprintf (stderr,
           "[cv2-0x89-resolver] original symbol resolved from target handle: "
           "%s\n",
           name);
  fprintf (stderr,
           "[cv2-0x89-resolver] dladdr target verification passed: %s\n",
           name);
  return true;
}

static void
initialize_resolver (void)
{
  const char *configured_path = getenv (CV2_TARGET_ENV);
  const char *configured_policy = getenv (CV2_UPDATE_POLICY_ENV);
  LoadedSearch search = { 0 };
  void *update_address;
  void *enrollment_started_address;
  const char *dynamic_error;

  if (!identity_from_path (configured_path, &search.expected))
    {
      resolver_failure ("invalid or missing %s: %s",
                        CV2_TARGET_ENV,
                        configured_path != NULL ? configured_path : "<unset>");
      return;
    }

  if (configured_policy == NULL ||
      strcmp (configured_policy, CV2_POLICY_LEGACY) == 0)
    resolver.update_policy = UPDATE_POLICY_LEGACY_REPEAT;
  else if (strcmp (configured_policy, CV2_POLICY_FRESH) == 0)
    resolver.update_policy = UPDATE_POLICY_FRESH_STOP_BEFORE_COMMIT;
  else if (strcmp (configured_policy, CV2_POLICY_FRESH_REARM) == 0)
    resolver.update_policy = UPDATE_POLICY_FRESH_REARM_STOP_BEFORE_COMMIT;
  else
    {
      resolver_failure ("invalid %s: %s",
                        CV2_UPDATE_POLICY_ENV,
                        configured_policy);
      return;
    }
  fprintf (stderr,
           "[cv2-enrollment-policy] selected=%s\n",
           update_policy_name (resolver.update_policy));
  fprintf (stderr,
           "[cv2-0x89-resolver] expected target path: %s\n",
           search.expected.path);

  dl_iterate_phdr (find_loaded_target, &search);
  if (!search.found)
    {
      resolver_failure (
        "expected target is not present in the loaded DSO list; refusing "
        "RTLD_NOLOAD lookup");
      return;
    }
  fprintf (stderr,
           "[cv2-0x89-resolver] loaded target discovered: %s\n",
           search.expected.path);

  dlerror ();
  resolver.handle = dlopen (search.expected.path, RTLD_LAZY | RTLD_NOLOAD);
  dynamic_error = dlerror ();
  if (resolver.handle == NULL || dynamic_error != NULL)
    {
      resolver.handle = NULL;
      resolver_failure ("RTLD_NOLOAD handle acquisition failed: %s",
                        dynamic_error != NULL ? dynamic_error : "unknown error");
      return;
    }
  fprintf (stderr,
           "[cv2-0x89-resolver] RTLD_NOLOAD handle acquired\n");

  dlerror ();
  update_address = dlsym (resolver.handle,
                          "cv_fingerprint_update_enrollment");
  dynamic_error = dlerror ();
  if (dynamic_error != NULL)
    update_address = NULL;
  if (!symbol_owned_by_target (
        update_address,
        "cv_fingerprint_update_enrollment",
        &search.expected,
        (void *) cv_fingerprint_update_enrollment))
    return;

  dlerror ();
  enrollment_started_address = dlsym (resolver.handle,
                                      "cv_cmd_enrollment_started");
  dynamic_error = dlerror ();
  if (dynamic_error != NULL)
    enrollment_started_address = NULL;
  if (!symbol_owned_by_target (enrollment_started_address,
                               "cv_cmd_enrollment_started",
                               &search.expected,
                               NULL))
    return;

  resolver.update =
    (cv_fingerprint_update_enrollment_fn) update_address;
  resolver.enrollment_started =
    (cv_cmd_enrollment_started_fn) enrollment_started_address;
  resolver.ready = true;
  fprintf (stderr,
           "[cv2-0x89-resolver] local-scope forwarding ready\n");
}

static bool
forwarding_ready (void)
{
  int once_status = pthread_once (&resolver_once, initialize_resolver);

  if (once_status != 0)
    {
      resolver_failure ("pthread_once failed: %s", strerror (once_status));
      return false;
    }
  return resolver.ready;
}

/*
 * Called by the repository-local hardware harness after FpContext has loaded
 * the TOD plugin, but before opening the device or starting enrollment.
 */
int
cv2_0x89_forwarding_ready (void)
{
  if (!forwarding_ready ())
    {
      fprintf (stderr,
               "[cv2-0x89-resolver] refusing operation before hardware "
               "command: %s\n",
               resolver.failure[0] != '\0'
                 ? resolver.failure
                 : "resolver is not ready");
      return 0;
    }
  return 1;
}

static uint32_t
fatalize_rearm_status (uint32_t status)
{
  if (status == CV_STATUS_BAD_CAPTURE ||
      status == CV_STATUS_CAPTURE_FAILED ||
      status == CV_STATUS_ENROLL_MORE)
    return CV_STATUS_EXPERIMENT_FAILURE;
  return status;
}

static void
log_update_outputs (const char *which,
                    const uint8_t *completion_out,
                    const void *enrollment_data_out,
                    const uint32_t *output_value_out)
{
  fprintf (stderr, "[cv2-0x59-experiment] %s completion=", which);
  if (completion_out == NULL)
    fprintf (stderr, "<null>");
  else
    fprintf (stderr, "0x%02x", (unsigned int) *completion_out);

  fprintf (stderr,
           " enrollment_output=%s output_value=%s\n",
           enrollment_data_out == NULL ? "<null>" : "<redacted>",
           output_value_out == NULL ? "<null>" : "<redacted>");
}

uint32_t
cv_fingerprint_update_enrollment (uint32_t handle,
                                  const void *enrollment_id,
                                  uint32_t auxiliary_input_size,
                                  const void *auxiliary_input,
                                  uint8_t *completion_out,
                                  void *enrollment_data_out,
                                  uint32_t *output_value_out)
{
  uint32_t status;
  uint32_t rearm_status;
  unsigned int attempt;

  if (!forwarding_ready ())
    {
      fprintf (stderr,
               "[cv2-0x89-resolver] refusing operation before hardware "
               "command: %s\n",
               resolver.failure[0] != '\0'
                 ? resolver.failure
                 : "resolver is not ready");
      return CV_STATUS_EXPERIMENT_FAILURE;
    }

  status = resolver.update (handle,
                            enrollment_id,
                            auxiliary_input_size,
                            auxiliary_input,
                            completion_out,
                            enrollment_data_out,
                            output_value_out);
  if (resolver.update_policy != UPDATE_POLICY_LEGACY_REPEAT)
    {
      fprintf (stderr,
               "[cv2-fresh-boundary] native UpdateEnrollment status=0x%x\n",
               status);
      log_update_outputs ("native",
                          completion_out,
                          enrollment_data_out,
                          output_value_out);
      if (status == CV_STATUS_UPDATE_AGAIN_EXPERIMENT)
        fprintf (stderr,
                 "[cv2-fresh-boundary] preserving native 0x59 without "
                 "same-update replay\n");
      if (status == CV_STATUS_SUCCESS &&
          (completion_out == NULL || *completion_out != 0))
        {
          fprintf (stderr,
                   "[cv2-fresh-boundary] native completion boundary "
                   "observed; blocking state 2 and generic commit\n");
          return CV_STATUS_EXPERIMENT_FAILURE;
        }
      if (resolver.update_policy ==
            UPDATE_POLICY_FRESH_REARM_STOP_BEFORE_COMMIT &&
          status == CV_STATUS_SUCCESS && completion_out != NULL &&
          *completion_out == 0)
        {
          unsigned int accepted = atomic_fetch_add_explicit (
                                    &accepted_incomplete_count,
                                    1,
                                    memory_order_relaxed)
                                  + 1;

          fprintf (stderr,
                   "[cv2-fresh-rearm] accepted incomplete update; "
                   "accepted=%u/%u\n",
                   accepted,
                   CV2_MAX_ACCEPTED_UPDATES);
          if (accepted >= CV2_MAX_ACCEPTED_UPDATES)
            {
              fprintf (stderr,
                       "[cv2-fresh-rearm] accepted-update limit reached "
                       "without native completion; blocking another "
                       "capture\n");
              return CV_STATUS_EXPERIMENT_FAILURE;
            }

          attempt = atomic_fetch_add_explicit (&retry_attempt,
                                               1,
                                               memory_order_relaxed)
                    + 1;
          fprintf (stderr,
                   "[cv2-fresh-rearm] re-arming accepted incomplete "
                   "enrollment with command 0x8A; attempt=%u\n",
                   attempt);
          rearm_status = resolver.enrollment_started ();
          if (rearm_status != CV_STATUS_SUCCESS)
            {
              fprintf (stderr,
                       "[cv2-fresh-rearm] 0x8A failed with status 0x%x; "
                       "attempt=%u\n",
                       rearm_status,
                       attempt);
              return fatalize_rearm_status (rearm_status);
            }
          fprintf (stderr,
                   "[cv2-fresh-rearm] 0x8A completed successfully; "
                   "attempt=%u\n",
                   attempt);
        }
    }
  else if (status == CV_STATUS_UPDATE_AGAIN_EXPERIMENT)
    {
      fprintf (stderr,
               "[cv2-0x59-experiment] 0x59 UpdateEnrollment result "
               "received\n");
      log_update_outputs ("first",
                          completion_out,
                          enrollment_data_out,
                          output_value_out);
      fprintf (stderr,
               "[cv2-0x59-experiment] retrying the same UpdateEnrollment "
               "once\n");

      status = resolver.update (handle,
                                enrollment_id,
                                auxiliary_input_size,
                                auxiliary_input,
                                completion_out,
                                enrollment_data_out,
                                output_value_out);
      fprintf (stderr,
               "[cv2-0x59-experiment] second UpdateEnrollment status=0x%x\n",
               status);
      log_update_outputs ("second",
                          completion_out,
                          enrollment_data_out,
                          output_value_out);
      if (status == CV_STATUS_UPDATE_AGAIN_EXPERIMENT)
        fprintf (stderr,
                 "[cv2-0x59-experiment] second 0x59 received; retry limit "
                 "reached\n");
      fprintf (stderr,
               "[cv2-0x59-experiment] passing second native status to "
               "existing Linux state machine\n");
    }

  if (status != CV_STATUS_BAD_CAPTURE)
    return status;

  attempt = atomic_fetch_add_explicit (&retry_attempt, 1, memory_order_relaxed)
            + 1;
  fprintf (stderr,
           "[cv2-0x89-experiment] 0x89 bad capture received; attempt=%u\n",
           attempt);
  fprintf (stderr,
           "[cv2-0x89-experiment] re-arming enrollment with command 0x8A; "
           "attempt=%u\n",
           attempt);

  rearm_status = resolver.enrollment_started ();
  if (rearm_status != CV_STATUS_SUCCESS)
    {
      fprintf (stderr,
               "[cv2-0x89-experiment] 0x8A failed with status 0x%x; "
               "attempt=%u\n",
               rearm_status,
               attempt);
      return fatalize_rearm_status (rearm_status);
    }

  fprintf (stderr,
           "[cv2-0x89-experiment] 0x8A completed successfully; attempt=%u\n",
           attempt);
  return CV_STATUS_BAD_CAPTURE;
}
