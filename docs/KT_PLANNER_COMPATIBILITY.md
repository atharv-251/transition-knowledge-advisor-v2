# KT Planner Compatibility

This document describes the additive compatibility contract between KT Planner
and KT Tracker. Existing KT Tracker fields and API payloads remain valid.

## Model Mapping

| KT Tracker model | KT Planner equivalent | Compatibility approach |
| --- | --- | --- |
| `KtPlan` | `Transition` | `source_transition_id` retains the Planner transition identifier. |
| `KtActivity` | Work tracked for a Transition, KT Session, or Knowledge Node | Optional source IDs retain Planner references without changing activity behavior. |
| `KtMeeting` | `KT Session` and Graph `Calendar Event` | `source_session_id` links a Planner session; `graph_event_id` remains the Calendar Event reference. |
| `MeetingParticipant` / activity owner and assignee | `Stakeholder` | `participant_id` retains the Graph user ID when available; `source_stakeholder_id` identifies the Planner stakeholder represented by the activity ownership context. |
| `MeetingAnalysisResult` | KT Session outcome | Continues to use `activity_id` and `external_meeting_id`; no duplicate Planner identifiers are required. |

## Field Mapping

| KT Planner field | KT Tracker field | Notes |
| --- | --- | --- |
| `Transition.id` | `KtPlan.source_transition_id` | Also copied to imported or Graph-created activities. |
| `KTSession.id` | `KtActivity.source_session_id`, `KtMeeting.source_session_id` | Optional Planner session correlation. |
| `KnowledgeNode.id` | `KtActivity.source_knowledge_node_id` | Identifies the knowledge content tracked by the activity. |
| `Stakeholder.id` | `KtActivity.source_stakeholder_id` | `owner` and `assignee` remain human-readable values. |
| Graph attendance user ID | `MeetingParticipant.participant_id` | Optional string identifier; existing `name` and `email` fields are unchanged. |
| Integration contract version | `contract_version` | Available on plans, activities, and meetings where applicable. |
| Calendar Event | `KtMeeting.graph_event_id` | Existing Graph event identifier; unchanged. |

## Status and Vocabulary

KT Tracker retains its existing `KtStatus`, `KtReadiness`, and
`KtMeetingStatus` values. No value is renamed or translated in this release,
because canonical KT Planner values for support level, approval status, and
session state have not been supplied. Future integration should exchange the
source IDs and `contract_version`, then add an explicit mapping only after the
Planner enum contract is finalized.