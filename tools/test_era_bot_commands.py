"""Compile and exercise the actual dispatcher against small core/playerbot fakes."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
COMPILER = shutil.which("c++") or shutil.which("g++") or shutil.which("clang++")


class EraBotPatchTests(unittest.TestCase):
    def test_command_patch_applies_to_existing_and_pristine_playerbots(self):
        checkout = ROOT / "deps/patch-validation-azerothcore/modules/mod-playerbots"
        if not checkout.is_dir() or not shutil.which("git"):
            self.skipTest("Local playerbots validation checkout unavailable")
        rel = "src/Ai/Base/Actions/ChangeTalentsAction.cpp"
        patch = ROOT / "patches/playerbots/03-era-talent-commands.patch"
        pristine = subprocess.check_output(["git", "-C", str(checkout), "show", "HEAD:" + rel])
        for content in (pristine, (checkout / rel).read_bytes()):
            with self.subTest(existing=content != pristine), tempfile.TemporaryDirectory() as temp:
                stage = Path(temp)
                target = stage / "modules/mod-playerbots" / rel
                target.parent.mkdir(parents=True)
                target.write_bytes(content)
                subprocess.run(["git", "apply", "--check", str(patch)], cwd=stage, check=True)
                subprocess.run(["git", "apply", str(patch)], cwd=stage, check=True)
                subprocess.run(["git", "apply", "--reverse", "--check", str(patch)], cwd=stage, check=True)


@unittest.skipUnless(COMPILER, "C++ compiler unavailable")
class EraBotCommandTests(unittest.TestCase):
    def test_native_fallback_and_era_commands(self):
        with tempfile.TemporaryDirectory() as temp:
            stage = Path(temp)
            fixtures = ROOT / "tools/fixtures"
            for header in ("AiFactory.h", "DBCStores.h", "Player.h", "Playerbots.h", "PlayerbotAI.h",
                           "PlayerbotAIConfig.h", "PlayerbotFactory.h",
                           "RandomPlayerbotMgr.h", "SpellMgr.h"):
                (stage / header).write_text('#include "era_bot_commands_stubs.h"\n')
            binary = stage / "era-bot-command-test"
            subprocess.run([COMPILER, "-std=c++17", "-Wall", "-Wextra", "-Werror",
                            "-DMOD_PLAYERBOTS", "-include", str(fixtures / "era_bot_commands_stubs.h"),
                            "-I", str(stage), "-I", str(fixtures), "-I", str(ROOT / "src"),
                            str(ROOT / "src/EraBotTalentCommands.cpp"),
                            str(fixtures / "era_bot_commands_test.cpp"), "-o", str(binary)], check=True)
            subprocess.run([str(binary)], check=True)


if __name__ == "__main__":
    unittest.main()
