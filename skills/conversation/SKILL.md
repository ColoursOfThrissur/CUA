# Conversation Skill

Handle conversations about the autonomous agent platform's capabilities, architecture, and features.

## Purpose
This skill handles conversational interactions about the platform as a solution:
- Questions about the platform's capabilities and tools
- Discussions about the platform's architecture and features
- Explanations of the platform's self-improvement systems
- General conversations about the platform

## When This Skill Activates
- Questions about the platform: "what can you do", "how does this work"
- Architecture discussions: "explain your skills system", "how do you improve"
- Feature explanations: "what tools do you have", "how does planning work"
- General platform conversations without action requirements

## Key Features
- **Platform-Focused**: All responses stay about the overall solution, not one subsystem
- **Architecture Aware**: References actual platform components
- **Solution-Oriented**: Discusses platform capabilities and features
- **No Generic AI**: Avoids generic AI assistant responses

## Output Types
- **architecture_explanation**: Details about the platform's systems
- **capability_overview**: List of the platform's tools and features
- **feature_discussion**: Explanation of specific platform functionality
- **solution_conversation**: General platform-focused dialogue

## Verification
- **Mode**: none (conversational responses)
- **Risk Level**: low (no system operations)

## Fallback Strategy
If conversation skill fails, ensure responses stay platform-focused.
