Feature: Structured output via batch agent run
  Verifies: .ai/spec/what/run-api.md (rules 18–20, structured response shaping)
  Verifies: .ai/spec/what/provider-contract.md (Structured output)
  Live contract tests via batch Jobs on a cluster (see scripts/e2e-containers.sh).

  Scenario: Run with flat schema and required fields
    Given the sandbox service is running
    And a flat output schema with required fields has been prepared
    When I run the agent with the prepared schema and query
    Then the run completes successfully
    And the response includes success summary and ticketId fields
    And the response JSON validates against the output schema

  Scenario: Run with nested schema
    Given the sandbox service is running
    And a nested output schema has been prepared
    When I run the agent with the prepared schema and query
    Then the run completes successfully
    And the response JSON validates against the output schema

  Scenario: Run without output schema
    Given the sandbox service is running
    And no output schema will be sent
    When I run the agent with the prepared query and no output schema
    Then the run completes successfully
    And the response has a non-empty summary
    And success is true

  Scenario: Adversarial schema returns a structured envelope
    Given the sandbox service is running
    And an adversarial output schema and prompt have been prepared
    When I run the agent with the prepared schema and query
    Then the run completes successfully and the envelope has success and summary
