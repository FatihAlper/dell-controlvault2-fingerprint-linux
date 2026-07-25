/*
 * Minimal staged harness for a repository-local libfprint-tod build.
 *
 * "probe" creates an FpContext and enumerates devices. libfprint only exposes
 * a device after its driver's probe callback succeeds. "open" additionally
 * calls the public open and close operations; it performs no enrollment,
 * verification, identification, listing, or deletion.
 */

#include <glib.h>
#include <libfprint/fprint.h>
#include <string.h>

static void
usage (const char *program)
{
  g_printerr ("Usage: %s --stage probe|open\n", program);
}

int
main (int argc, char **argv)
{
  g_autoptr(FpContext) context = NULL;
  g_autoptr(GError) error = NULL;
  GPtrArray *devices;
  FpDevice *device = NULL;
  const char *stage;
  guint i;

  if (argc != 3 || strcmp (argv[1], "--stage") != 0)
    {
      usage (argv[0]);
      return 64;
    }

  stage = argv[2];
  if (strcmp (stage, "probe") != 0 && strcmp (stage, "open") != 0)
    {
      usage (argv[0]);
      return 64;
    }

  context = fp_context_new ();
  fp_context_enumerate (context);
  devices = fp_context_get_devices (context);

  g_print ("enumerated_devices=%u\n", devices->len);
  for (i = 0; i < devices->len; i++)
    {
      FpDevice *candidate = g_ptr_array_index (devices, i);

      g_print ("device[%u]: driver=%s name=%s\n",
               i,
               fp_device_get_driver (candidate),
               fp_device_get_name (candidate));
      if (g_strcmp0 (fp_device_get_driver (candidate), "broadcom") == 0)
        device = candidate;
    }

  if (!device)
    {
      g_printerr ("probe_failed: no Broadcom device survived initialization\n");
      return 2;
    }

  g_print ("probe_passed: Broadcom device is available through FpContext\n");
  if (strcmp (stage, "probe") == 0)
    return 0;

  if (!fp_device_open_sync (device, NULL, &error))
    {
      g_printerr ("open_failed: %s\n", error->message);
      return 3;
    }
  g_print ("open_passed: device opened through the TOD plugin\n");

  g_clear_error (&error);
  if (!fp_device_close_sync (device, NULL, &error))
    {
      g_printerr ("close_failed: %s\n", error->message);
      return 4;
    }
  g_print ("close_passed: device closed cleanly\n");
  return 0;
}
