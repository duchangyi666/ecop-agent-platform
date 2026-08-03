import { Badge } from "./badge";
import type { Tone } from "./badge";

/** Map a domain status value to a colored badge. */
export function StatusBadge({ value, label }: { value: string | null | undefined; label: string }) {
  const tone = statusTone(value);
  return <Badge tone={tone}>{label}</Badge>;
}

export function statusTone(value: string | null | undefined): Tone {
  switch (value) {
    case "open":
    case "in_progress":
    case "pending":
    case "pending_customer":
    case "requested":
      return "blue";
    case "resolved":
    case "closed":
    case "approved":
    case "succeeded":
    case "completed":
    case "active":
      return "emerald";
    case "pending_approval":
    case "more_information_required":
    case "modified":
    case "unknown_execution_state":
    case "requires_action":
      return "amber";
    case "escalated":
    case "rejected":
    case "failed":
    case "cancelled":
    case "expired":
      return "red";
    case "reopened":
    case "unknown":
      return "violet";
    default:
      return "neutral";
  }
}
