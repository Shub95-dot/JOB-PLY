"""Manager for loading, updating, and saving candidate profile data."""

import os
from typing import Optional, Dict, Any, List
import yaml
from src.core.models import Profile
from src.core.utils import load_yaml, setup_logger

logger = setup_logger("profile_manager")


class ProfileManager:
    """Manages candidate Profile loading, updates, and persistence."""

    def __init__(self, profile_path: str = "config/user_profile.yaml"):
        self.profile_path = profile_path
        self._profile: Optional[Profile] = None

    def load_profile(self) -> Profile:
        """Load candidate profile from YAML file."""
        if not os.path.exists(self.profile_path):
            logger.warning(f"Profile path {self.profile_path} not found. Creating default empty profile.")
            self._profile = Profile(name="Shubham")
            return self._profile

        data = load_yaml(self.profile_path)
        self._profile = Profile(**data)
        logger.info(f"Loaded profile for {self._profile.name}")
        return self._profile

    def get_profile(self) -> Profile:
        """Returns active profile, loading if not already cached."""
        if self._profile is None:
            return self.load_profile()
        return self._profile

    def update_skills(self, new_skills: List[str]) -> Profile:
        """Update candidate skills list."""
        profile = self.get_profile()
        updated_skills = list(set(profile.skills + new_skills))
        profile.skills = updated_skills
        self._profile = profile
        return self._profile

    def add_project(self, project: Dict[str, Any]) -> Profile:
        """Add a project to candidate profile."""
        profile = self.get_profile()
        profile.projects.append(project)
        self._profile = profile
        return self._profile

    def save_profile(self, target_path: Optional[str] = None) -> None:
        """Persist candidate profile back to YAML file."""
        profile = self.get_profile()
        path = target_path or self.profile_path
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(profile.model_dump(), f, default_flow_style=False, sort_keys=False)
        logger.info(f"Saved updated profile to {path}")
