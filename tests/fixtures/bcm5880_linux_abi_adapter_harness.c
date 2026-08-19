#include "bcm5880_enrollment_coordinator.h"
#include "bcm5880_linux_abi_adapter.h"

#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef struct
{
  const char *scenario;
  unsigned int capture_calls;
  unsigned int template_calls;
  unsigned int random_calls;
} HarnessState;

static HarnessState state;

static uint32_t
native_capture_get_result (
  uint32_t handle,
  uint8_t result_selector,
  const uint8_t capture_id[CV2_BCM5880_ENROLLMENT_ID_SIZE],
  uint32_t *feature_size_inout,
  uint8_t *feature_out)
{
  state.capture_calls++;
  if (handle != 0x11223344u || result_selector != 0x5au ||
      *feature_size_inout != CV2_BCM5880_FEATURE_CAPACITY)
    abort ();
  for (unsigned int index = 0; index < CV2_BCM5880_ENROLLMENT_ID_SIZE;
       index++)
    if (capture_id[index] != (uint8_t) (0x30u + index))
      abort ();

  feature_out[0] = 0x61;
  if (strcmp (state.scenario, "capture-overflow") == 0)
    {
      *feature_size_inout = CV2_BCM5880_FEATURE_CAPACITY + 1;
      return 0;
    }
  *feature_size_inout = 0x120;
  if (strcmp (state.scenario, "capture-native-status") == 0)
    return 0x8f;
  return 0;
}

static uint32_t
native_create_template (
  uint32_t handle,
  uint32_t feature0_size,
  const uint8_t *feature0,
  uint32_t feature1_size,
  const uint8_t *feature1,
  uint32_t feature2_size,
  const uint8_t *feature2,
  uint32_t feature3_size,
  const uint8_t *feature3,
  uint32_t *template_size_inout,
  uint8_t *template_out)
{
  const uint32_t sizes[CV2_BCM5880_TEMPLATE_FEATURES] = {
    feature0_size, feature1_size, feature2_size, feature3_size
  };
  const uint8_t *features[CV2_BCM5880_TEMPLATE_FEATURES] = {
    feature0, feature1, feature2, feature3
  };

  state.template_calls++;
  if (handle != 7 || *template_size_inout != CV2_BCM5880_TEMPLATE_CAPACITY)
    abort ();
  for (unsigned int index = 0; index < CV2_BCM5880_TEMPLATE_FEATURES;
       index++)
    if (sizes[index] != 100u + index || features[index] == NULL ||
        features[index][0] != (uint8_t) (0x10u + index))
      abort ();

  template_out[0] = 0xa5;
  if (strcmp (state.scenario, "template-overflow") == 0)
    {
      *template_size_inout = CV2_BCM5880_TEMPLATE_CAPACITY + 1;
      return 0;
    }
  *template_size_inout = 64;
  return 0;
}

static int
mock_random_bytes (void *user_data, uint8_t *output, size_t size)
{
  if (user_data == NULL || size != CV2_BCM5880_TOKEN_RANDOM_PREFIX_SIZE)
    abort ();
  state.random_calls++;
  memset (output, 0x5a, size);
  return 0;
}

static int
run_capture (Cv2Bcm5880LinuxAbiMock *adapter)
{
  uint8_t capture_id[CV2_BCM5880_ENROLLMENT_ID_SIZE];
  uint8_t feature[CV2_BCM5880_FEATURE_CAPACITY];
  uint32_t feature_size = sizeof feature;
  uint32_t status;

  for (unsigned int index = 0; index < sizeof capture_id; index++)
    capture_id[index] = (uint8_t) (0x30u + index);
  memset (feature, 0xcc, sizeof feature);
  status = cv2_bcm5880_linux_abi_mock_capture_get_result (
    adapter, 0x11223344u, 0x5a, capture_id, &feature_size, feature);
  printf ("capture status=0x%x size=%u first=0x%02x calls=%u\n",
          status,
          feature_size,
          feature[0],
          state.capture_calls);
  return 0;
}

static int
run_coordinator (Cv2Bcm5880LinuxAbiMock *adapter)
{
  uint8_t enrollment_id[CV2_BCM5880_ENROLLMENT_ID_SIZE];
  uint8_t feature[CV2_BCM5880_FEATURE_CAPACITY];
  Cv2Bcm5880MockConfig config = { 0 };
  Cv2Bcm5880MockCoordinator *coordinator;
  Cv2Bcm5880Error error;
  Cv2Bcm5880Outcome outcome = CV2_BCM5880_OUTCOME_REJECTED;
  Cv2Bcm5880Snapshot snapshot;

  memset (enrollment_id, 0x31, sizeof enrollment_id);
  config.mode = CV2_BCM5880_EXECUTION_MOCK_ONLY;
  config.handle = 7;
  config.enrollment_id = enrollment_id;
  config.operations.create_template =
    cv2_bcm5880_linux_abi_mock_create_template;
  config.operations.random_bytes = mock_random_bytes;
  config.operations.user_data = adapter;
  coordinator = cv2_bcm5880_mock_coordinator_new (&config, &error);
  if (coordinator == NULL)
    abort ();

  for (unsigned int index = 0; index < CV2_BCM5880_TEMPLATE_FEATURES;
       index++)
    {
      memset (feature, (int) (0x10u + index), sizeof feature);
      outcome = cv2_bcm5880_mock_coordinator_accept_feature (
        coordinator, enrollment_id, feature, 100u + index);
    }
  snapshot = cv2_bcm5880_mock_coordinator_snapshot (coordinator);
  printf ("coordinator outcome=%u ready=%u size=%u commit=%u terminal=%u "
          "error=%s native=0x%x template_calls=%u random_calls=%u\n",
          (unsigned int) outcome,
          snapshot.template_ready ? 1u : 0u,
          snapshot.template_size,
          snapshot.commit_permitted ? 1u : 0u,
          snapshot.terminal ? 1u : 0u,
          cv2_bcm5880_error_name (snapshot.last_error),
          snapshot.last_native_status,
          state.template_calls,
          state.random_calls);
  cv2_bcm5880_mock_coordinator_free (coordinator);
  return 0;
}

int
main (int argc, char **argv)
{
  Cv2Bcm5880LinuxAbiMockConfig config = { 0 };
  Cv2Bcm5880LinuxAbiMock adapter = { 0 };
  Cv2Bcm5880AbiError error;

  if (argc != 2)
    return 64;
  memset (&state, 0, sizeof state);
  state.scenario = argv[1];
  config.mode = strcmp (state.scenario, "disabled") == 0
                  ? CV2_BCM5880_EXECUTION_DISABLED
                  : CV2_BCM5880_EXECUTION_MOCK_ONLY;
  config.capture_get_result = native_capture_get_result;
  config.create_template = native_create_template;
  if (strcmp (state.scenario, "missing-native") == 0)
    config.create_template = NULL;

  if (!cv2_bcm5880_linux_abi_mock_init (&adapter, &config, &error))
    {
      printf ("init=failed error=%s capture_calls=%u template_calls=%u\n",
              cv2_bcm5880_abi_error_name (error),
              state.capture_calls,
              state.template_calls);
      return 0;
    }

  if (strncmp (state.scenario, "capture", 7) == 0)
    run_capture (&adapter);
  else
    run_coordinator (&adapter);
  cv2_bcm5880_linux_abi_mock_clear (&adapter);
  return 0;
}
