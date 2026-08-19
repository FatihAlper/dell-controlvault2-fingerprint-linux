from pathlib import Path
import shutil
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
TRACE = TOOLS / "windows_a21_enrollment_trace.js"
RUNNER = TOOLS / "run_windows_a21_enrollment_trace.ps1"


class WindowsA21EnrollmentTraceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.trace = TRACE.read_text(encoding="utf-8")
        cls.runner = RUNNER.read_text(encoding="utf-8")

    def test_trace_is_valid_javascript(self):
        node = shutil.which("node")
        if node is None:
            self.skipTest("node is unavailable")
        result = subprocess.run(
            [node, "--check", str(TRACE)],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_trace_has_exact_a21_hooks_and_selector(self):
        required = (
            "CSS_FingerprintCaptureStart",
            "CSS_FingerprintSetCaptureMode",
            "CSS_FingerprintUpdateEnrollment",
            "CSS_FingerprintCommitEnrollment",
            "CSS_FingerprintCommitFeatureSet",
            "CSS_FingerprintDiscardEnrollment",
            "cv_fingerprint_commit_enrollment",
            "cv_fingerprint_commit_feature_set",
            "cv_fingerprint_discard_enrollment",
            "UPDATE_SELECTOR_TEST_RVA = 0x2d249",
        )
        for value in required:
            with self.subTest(value=value):
                self.assertIn(value, self.trace)

    def test_trace_cannot_dump_or_retain_payloads(self):
        forbidden_apis = (
            "readByteArray",
            "readCString",
            "readUtf8String",
            "readUtf16String",
            "hexdump",
            "Memory.scan",
            "Memory.write",
            "writeByteArray",
            "send(",
        )
        for value in forbidden_apis:
            with self.subTest(value=value):
                self.assertNotIn(value, self.trace)
        self.assertEqual(self.trace.count("console.log("), 1)
        self.assertIn("payload_logging: 'disabled'", self.trace)
        self.assertIn("pointer_logging: 'disabled'", self.trace)
        self.assertNotIn("String(error)", self.trace)
        self.assertIn("reason: 'hook_install_failed'", self.trace)

    def test_runner_requires_confirmation_before_process_inspection(self):
        guard = self.runner.index("if (-not $ConfirmPrivacySafeTrace)")
        process_lookup = self.runner.index("Get-Process")
        frida_launch = self.runner.index("& $frida.Source")
        self.assertLess(guard, process_lookup)
        self.assertLess(guard, frida_launch)
        self.assertIn("Find-A21HostProcess", self.runner)

    def test_runner_pins_all_loaded_module_hashes(self):
        expected = (
            "30c556a9b542d0fcf29a6822b3bb81fe23ce2917b403b3f25af9384e0e31e524",
            "622b1a12566cb313cde264869ca5a4b410e3d5b2b604f5dd628c4a6b709b19ae",
            "dfb30d81de42e726477b103412fba2c88abd9b675ead7141f25063a3ac8d4e6c",
        )
        for digest in expected:
            with self.subTest(digest=digest):
                self.assertIn(digest, self.runner)
        self.assertIn("Get-FileHash -Algorithm SHA256", self.runner)

    def test_runner_does_not_modify_services_registry_or_driver_files(self):
        forbidden_commands = (
            "Start-Service",
            "Stop-Service",
            "Restart-Service",
            "Set-ItemProperty",
            "New-ItemProperty",
            "Remove-ItemProperty",
            "reg.exe",
            "pnputil",
            "Copy-Item",
            "Move-Item",
            "Remove-Item",
        )
        for value in forbidden_commands:
            with self.subTest(value=value):
                self.assertNotIn(value, self.runner)
        self.assertIn('Write-Host "binary_modification=none"', self.runner)


if __name__ == "__main__":
    unittest.main()
