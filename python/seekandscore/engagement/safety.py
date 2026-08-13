"""Safe engagement capability status; this module sends no communications."""

from pydantic import BaseModel, ConfigDict

from seekandscore.platform.settings import OutreachMode, Settings


class EngagementSafetyStatus(BaseModel):
    model_config = ConfigDict(frozen=True)

    mode: OutreachMode
    send_enabled: bool
    human_approval_required: bool
    policy_id: str
    fail_closed: bool = True

    @classmethod
    def from_settings(cls, settings: Settings) -> "EngagementSafetyStatus":
        return cls(
            mode=settings.outreach_mode,
            send_enabled=settings.outreach_send_enabled,
            human_approval_required=settings.outreach_human_approval_required,
            policy_id=settings.outreach_policy_id,
        )

    @property
    def is_safe(self) -> bool:
        if not self.send_enabled:
            return True
        return self.mode is OutreachMode.PROVIDER and self.human_approval_required
