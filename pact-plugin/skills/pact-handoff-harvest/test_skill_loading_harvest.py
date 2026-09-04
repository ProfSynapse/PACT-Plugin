"""
pact-plugin/skills/pact-handoff-harvest/test_skill_loading_harvest.py

Tests for verifying the pact-handoff-harvest skill file structure and content.
Ensures SKILL.md exists, has valid YAML frontmatter, includes all three workflow
variants, supporting sections, keyword routing, and critical protocol references.
"""

import pytest
from pathlib import Path
import yaml


SKILL_DIR = Path(__file__).parent
SKILL_FILE = SKILL_DIR / "SKILL.md"
AGENTS_DIR = SKILL_DIR.parent.parent / "agents"
SECRETARY_FILE = AGENTS_DIR / "pact-secretary.md"

ORPHAN_HEADING = "## Orphaned Handoff Recovery"

# A known sentence of the Orphaned Handoff Recovery section, used as the
# anchor of the non-vacuity guard. It must sit in that section and in no
# other.
ORPHAN_ANCHOR = "Layer 4 fallback"

# Call spellings that remove a file from disk. THIS LIST IS A FLOOR AND NOT
# A PROOF OF ABSENCE: prose can authorise a removal in words no list
# anticipates. The POSITIVE assertion carries the contract. This list catches
# the machine-shaped forms an editor pastes back in.
REMOVAL_CALL_TOKENS = ("unlink", "shutil.rmtree", "os.remove", "os.rmdir", "rm -")


def orphan_recovery_section(content):
    """Return the Orphaned Handoff Recovery section of the skill.

    The slice runs from the section heading to the next `## ` heading, or to
    the end of the file when that section is the last one. THE SLICE RULE IS
    THE PARAMETER OF THE ARM BELOW, so the arm asserts the slice terminated
    correctly before it reads anything out of it.
    """
    start = content.find(ORPHAN_HEADING)
    if start == -1:
        return ""
    rest = content[start + len(ORPHAN_HEADING):]
    end = rest.find("\n## ")
    return rest if end == -1 else rest[:end]


@pytest.fixture
def skill_content():
    """Load the skill file content."""
    return SKILL_FILE.read_text()


@pytest.fixture
def secretary_content():
    """Load the secretary agent definition."""
    return SECRETARY_FILE.read_text()


class TestPopulationPrecedence:
    """The dispatch-is-a-hint rule, and that it arrives before Step 1.

    A secretary that reads the rule only AFTER constructing the population has
    already mis-scoped, so presence alone is not enough: the rule must sit
    ahead of Step 1."""

    def test_rule_present(self, skill_content):
        assert "DISCARD ANY SCOPE YOU ARRIVED WITH" in skill_content
        assert "A dispatch that names tasks has given you one." in skill_content
        assert "never the population" in skill_content
        assert "outranks a dispatch that contradicts it" in skill_content

    def test_ledger_settles_the_population(self, skill_content):
        """Step 1 constructs the population; the ledger settles it. A reader
        can run the census and still trim to a dispatch range, so Step 2
        carries its own refusal."""
        assert "A dispatch-named task set does not narrow this list." in skill_content

    def test_workflow_selection_is_not_scope_authority(self, secretary_content):
        """The persona sentence a secretary holds BEFORE it opens the skill
        must not read as authority over which tasks are in scope."""
        assert "never which tasks are in scope" in secretary_content
        assert "workflow as directed by task descriptions" not in secretary_content

    def test_rule_precedes_step_1(self, skill_content):
        rule = skill_content.find("DISCARD ANY SCOPE YOU ARRIVED WITH")
        step1 = skill_content.find("### Step 1: Task Discovery")
        assert rule != -1 and step1 != -1
        assert rule < step1, "the rule must arrive before the population is built"


class TestSkillFileExists:
    """Test that the skill file exists."""

    def test_skill_md_exists(self):
        """SKILL.md file must exist in the skill directory."""
        assert SKILL_FILE.exists(), f"SKILL.md not found at {SKILL_FILE}"

    def test_skill_md_is_file(self):
        """SKILL.md must be a regular file, not a directory."""
        assert SKILL_FILE.is_file(), f"{SKILL_FILE} exists but is not a file"


class TestYamlFrontmatter:
    """Test that YAML frontmatter is valid and has required fields."""

    @pytest.fixture
    def frontmatter(self, skill_content):
        """Extract and parse YAML frontmatter from skill file."""
        if not skill_content.startswith("---"):
            pytest.fail("SKILL.md must start with YAML frontmatter (---)")

        end_marker = skill_content.find("---", 3)
        if end_marker == -1:
            pytest.fail("SKILL.md has unclosed YAML frontmatter")

        yaml_content = skill_content[3:end_marker].strip()
        return yaml.safe_load(yaml_content)

    def test_has_name_field(self, frontmatter):
        """Frontmatter must include 'name' field."""
        assert "name" in frontmatter, "YAML frontmatter must include 'name' field"
        assert frontmatter["name"], "'name' field must not be empty"

    def test_has_description_field(self, frontmatter):
        """Frontmatter must include 'description' field."""
        assert "description" in frontmatter, "YAML frontmatter must include 'description' field"
        assert frontmatter["description"], "'description' field must not be empty"

    def test_name_matches_directory(self, frontmatter):
        """Skill name should match the directory name."""
        expected_name = SKILL_DIR.name
        assert frontmatter["name"] == expected_name, (
            f"Skill name '{frontmatter['name']}' should match directory name '{expected_name}'"
        )


class TestWorkflowSections:
    """Test that all three workflow variants are present."""

    def test_has_standard_harvest(self, skill_content):
        """Skill must include Standard Harvest Workflow section."""
        assert "## Standard Harvest Workflow" in skill_content

    def test_has_incremental_harvest(self, skill_content):
        """Skill must include Incremental Harvest Workflow section."""
        assert "## Incremental Harvest Workflow" in skill_content

    def test_has_consolidation_harvest(self, skill_content):
        """Skill must include Consolidation Harvest Workflow section."""
        assert "## Consolidation Harvest Workflow" in skill_content

    def test_section_ordering(self, skill_content):
        """Workflows must be ordered: Standard → Incremental → Consolidation."""
        standard_pos = skill_content.index("## Standard Harvest Workflow")
        incremental_pos = skill_content.index("## Incremental Harvest Workflow")
        consolidation_pos = skill_content.index("## Consolidation Harvest Workflow")
        assert standard_pos < incremental_pos < consolidation_pos, (
            "Workflow ordering must be Standard → Incremental → Consolidation"
        )


class TestSupportingSections:
    """Test that supporting sections are present."""

    def test_has_knowledge_extraction_guide(self, skill_content):
        """Skill must include Knowledge Extraction Guide section."""
        assert "## Knowledge Extraction Guide" in skill_content

    def test_has_investigation_protocol(self, skill_content):
        """Skill must include Investigation Protocol section."""
        assert "## Investigation Protocol" in skill_content

    def test_has_ad_hoc_saves(self, skill_content):
        """Skill must include Ad-Hoc Save Requests section."""
        assert "## Ad-Hoc Save Requests" in skill_content

    def test_has_orphaned_handoff_recovery(self, skill_content):
        """Skill must include Orphaned Handoff Recovery section."""
        assert "## Orphaned Handoff Recovery" in skill_content


class TestKeywordRouting:
    """Test that keyword routing maps trigger keywords to correct workflow variants."""

    @staticmethod
    def _routing_lines(content):
        """Extract lines from the keyword routing paragraph (near top of skill)."""
        return [line for line in content.splitlines() if "→" in line]

    def test_routes_harvest_keyword(self, skill_content):
        """Routing must map 'harvest' to Standard Harvest on the same line."""
        lines = self._routing_lines(skill_content)
        assert any('"harvest"' in line and "Standard Harvest" in line for line in lines), (
            "No routing line maps \'harvest\' to Standard Harvest"
        )

    def test_routes_incremental_keyword(self, skill_content):
        """Routing must map 'incremental' to Incremental Harvest on the same line."""
        lines = self._routing_lines(skill_content)
        assert any('"incremental"' in line and "Incremental Harvest" in line for line in lines), (
            "No routing line maps \'incremental\' to Incremental Harvest"
        )

    def test_routes_consolidation_keyword(self, skill_content):
        """Routing must map 'consolidation' to Consolidation Harvest on the same line."""
        lines = self._routing_lines(skill_content)
        assert any('"consolidation"' in line and "Consolidation Harvest" in line for line in lines), (
            "No routing line maps \'consolidation\' to Consolidation Harvest"
        )

    def test_routes_process_handoffs_keyword(self, skill_content):
        """Routing must map 'process HANDOFFs' to Standard Harvest on the same line."""
        lines = self._routing_lines(skill_content)
        assert any("process HANDOFF" in line and "Standard Harvest" in line for line in lines), (
            "No routing line maps \'process HANDOFFs\' to Standard Harvest"
        )

    def test_routes_remediation_keyword(self, skill_content):
        """Routing must map 'remediation' to Incremental Harvest on the same line."""
        lines = self._routing_lines(skill_content)
        assert any('"remediation"' in line and "Incremental Harvest" in line for line in lines), (
            "No routing line maps \'remediation\' to Incremental Harvest"
        )


class TestSecretaryIntegration:
    """Test that the secretary agent definition loads this skill."""

    def test_secretary_frontmatter_includes_skill(self, secretary_content):
        """Secretary frontmatter skills list must include pact-handoff-harvest."""
        assert "pact-handoff-harvest" in secretary_content, (
            "pact-secretary.md must list pact-handoff-harvest in frontmatter skills"
        )


class TestCriticalProtocolReferences:
    """Test that critical protocol references are present in the skill."""

    def test_has_calibration_record_reference(self, skill_content):
        """Skill must reference CalibrationRecord for variety scoring feedback."""
        assert "CalibrationRecord" in skill_content

    def test_orphan_recovery_records_and_removes_nothing(self, skill_content):
        """The recovery step must RECORD the processed ids and remove no file.

        THIS ARM REPLACES A PIN ON THE OPPOSITE CONTRACT. It used to assert
        that the skill referenced `Path.unlink`, because step 4 told the
        agent how to remove the files it had read. Either of the two file
        classes that step reads can be the ONLY carrier of a HANDOFF, so the
        step was changed to record the ids into the Step 8 ledger and to
        remove nothing. A pin demanding the removed instruction is a pin on
        a defect.

        Deleting the assertion was the other option and it is worse. This
        class is colocated with the skill, so it is the arm a reader of the
        skill directory meets, and a member that asserts nothing reads as
        coverage while it gives none.

        THE THREE PARTS RUN IN THIS ORDER AND THE ORDER IS LOAD-BEARING.
        The non-vacuity guard runs FIRST: a negative assertion on an empty
        or mis-sliced section passes forever while it measures nothing.
        Then the positive assertion carries the contract. Then the negative
        assertion catches a machine-shaped removal pasted back in.

        WHAT THIS CANNOT CATCH: the token list is a FLOOR. An instruction
        that says erase the file in plain words passes the negative part.
        The positive part is what pins the contract itself.

        A sibling arm, `TestOrphanRecoveryCarrierGuard` in
        `tests/test_skills_structure.py`, pins three carrier-test phrases of
        the same section. This arm deliberately does NOT repeat them. It
        carries the SECTION-SCOPED ABSENCE term, which no other arm covers.
        """
        section = orphan_recovery_section(skill_content)

        # --- NON-VACUITY GUARD. Four checks, and each must pass before the
        # --- assertions below can mean anything.
        assert section.strip(), (
            f"The {ORPHAN_HEADING!r} section is empty or absent, so the "
            f"assertions below would pass while measuring nothing. Either "
            f"the section was removed from the skill, or the slice rule in "
            f"orphan_recovery_section no longer finds its heading."
        )
        assert len(section) < len(skill_content), (
            "The section slice is the whole file, so the scope of this arm "
            "ran away and the absence check below covers text it must not."
        )
        assert ORPHAN_ANCHOR in section, (
            f"The section slice does not contain {ORPHAN_ANCHOR!r}, so it is "
            f"not the section this arm targets. Update ORPHAN_ANCHOR only "
            f"after checking the sentence moved rather than the slice."
        )
        assert "\n## " not in section, (
            "The section slice contains a later heading, so it did not "
            "terminate at the section boundary."
        )

        # --- POSITIVE. The contract the step carries now.
        assert "Do NOT remove the files you read them from" in section, (
            "The Orphaned Handoff Recovery step must tell the agent to "
            "record the processed ids and to remove no file. Its absence "
            "means the step could have reverted to a removal, and either "
            "file class it reads can be the ONLY carrier of a recovered "
            "HANDOFF. If a deliberate rewording changed the phrase, update "
            "it here and state in the update that the step removes nothing."
        )

        # --- NEGATIVE. A floor, not a proof of absence.
        for token in REMOVAL_CALL_TOKENS:
            assert token not in section, (
                f"The Orphaned Handoff Recovery step contains {token!r}, "
                f"which removes a file. That step reads the session journal "
                f"and the task files, and either can be the only carrier of "
                f"a HANDOFF, so it must record the ids and remove nothing. "
                f"REMOVAL_CALL_TOKENS is a floor: seeing one is proof of a "
                f"regression, and seeing none is not proof of safety."
            )

    def test_has_processed_tasks_tracking(self, skill_content):
        """Skill must reference processed task tracking for dedup."""
        assert "processed_tasks" in skill_content or "session_processed_tasks" in skill_content, (
            "Skill must reference processed task tracking for incremental dedup"
        )
