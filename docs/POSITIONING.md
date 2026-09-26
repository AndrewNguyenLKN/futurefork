# Positioning and prior art

## Category

FutureFork is an **architecture rehearsal** tool, not a generic code reviewer, test generator, roadmap predictor, or autonomous feature factory.

## Defensible differentiation

The differentiating workflow is:

```text
two correct designs today
        +
identical bounded future-change tasks
        +
actual Bob implementations in isolated forks
        +
independent protected evaluation
        ↓
evidence for a present-day design decision
```

No individual ingredient is claimed to be new. The product hypothesis is that combining them into a developer decision loop is useful and demonstrable.

## Relevant prior art

### Scenario-based architecture evaluation

CMU SEI's SAAM/ATAM tradition evaluates architecture using concrete change scenarios. FutureFork follows that sound principle but attempts the changes in code with an AI development agent and records executable evidence.

Reference: <https://www.sei.cmu.edu/history-of-innovation/evaluating-system-architecture/>

### Long-horizon agent evaluation

SWE-EVO evaluates coding agents on multi-step software evolution drawn from project history. FutureFork reverses the evaluation target: the agent and scenario are held as constant as practical while code candidates are compared to inform a current design decision.

Reference: <https://github.com/SWE-EVO/SWE-EVO>

### Code review and test generation

Existing tools inspect patches, generate tests, or predict risk. FutureFork's center of gravity is a set of disposable future implementations with protected acceptance evidence. Static analysis may become an input, but it is not the product's proof.

## Comparison language

Use:

- “FutureFork executes bounded change rehearsals.”
- “The evidence is specific to the selected scenarios and limits.”
- “Bob performs the implementation; protected tests evaluate it.”
- “The user makes the design decision.”

Avoid:

- “First ever” or “world's only.”
- “Predicts the future.”
- “Proves maintainability.”
- “Eliminates technical debt.”
- “Objective architecture score.”

## Why now

Scenario-based architecture evaluation previously required expensive manual prototypes. Coding agents make multiple disposable implementations plausible within a developer workflow. The opportunity is not merely faster code generation; it is using generated work as evidence before making a durable decision.

## Expected objections

### “The agent may simply be better at one code style.”

Correct. FutureFork must disclose this and use neutral labels, equal context, frozen limits, repeated runs when possible, and raw artifacts. It measures the combined interaction between candidate, scenario, and agent—not intrinsic architecture quality.

### “The future requirements may never happen.”

Correct. Scenarios are hypotheses. Users choose plausible, decision-relevant changes from their roadmap. FutureFork supports a decision under stated assumptions; it does not forecast demand.

### “A senior architect could already reason about this.”

Yes. FutureFork turns that reasoning into inspectable prototypes and test outcomes, helping validate or challenge expert judgment. It is an instrument for architecture review, not its replacement.

### “You can game the result with tests.”

Yes. Therefore test provenance, frozen hashes, held-out scenarios, and transparent artifacts are part of the product—not optional methodology.

