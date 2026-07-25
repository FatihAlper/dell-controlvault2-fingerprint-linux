import struct
import unittest

import patch_driver


def synthetic_binary(patches):
    return b"\x90PADDING\x90".join(patch.find for patch in patches)


class PatchDriverTests(unittest.TestCase):
    def test_5833_probe_patch_set_has_only_probe_changes(self):
        patches = patch_driver.make_patches(0x5833, "probe")
        self.assertEqual(len(patches), 3)
        self.assertEqual(
            patches[0].replace,
            struct.pack("<II", 0x5833, patch_driver.VENDOR_ID),
        )
        descriptions = " ".join(patch.description for patch in patches)
        self.assertNotIn("enroll", descriptions)
        self.assertNotIn("verify", descriptions)

    def test_probe_patches_apply_once(self):
        patches = patch_driver.make_patches(0x5833, "probe")
        source = synthetic_binary(patches)
        result = patch_driver.apply_patches(source, patches)
        for patch in patches:
            self.assertNotIn(patch.find, result)
            self.assertEqual(result.count(patch.replace), 1)

    def test_missing_signature_is_rejected(self):
        patches = patch_driver.make_patches(0x5833, "probe")
        with self.assertRaisesRegex(patch_driver.PatchError, "signature not found"):
            patch_driver.apply_patches(b"not a driver", patches)

    def test_ambiguous_signature_is_rejected(self):
        patch = patch_driver.make_patches(0x5833, "probe")[0]
        with self.assertRaisesRegex(patch_driver.PatchError, "ambiguous"):
            patch_driver.apply_patches(patch.find + patch.find, (patch,))

    def test_unvalidated_pid_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "unvalidated"):
            patch_driver.make_patches(0x9999, "probe")

    def test_5833_full_patch_set_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "probe patch set"):
            patch_driver.make_patches(0x5833, "full")


if __name__ == "__main__":
    unittest.main()
