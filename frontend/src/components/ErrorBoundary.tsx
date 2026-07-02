import { Component, type ReactNode } from "react";
import { Button, Code, Container, Stack, Text, Title } from "@mantine/core";

/** Top-level error boundary so a render crash shows a recoverable message
 * instead of a blank white screen. */
export class ErrorBoundary extends Component<
  { children: ReactNode },
  { error: Error | null }
> {
  constructor(props: { children: ReactNode }) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <Container size="sm" py="xl">
        <Stack>
          <Title order={3}>Something went wrong</Title>
          <Text c="dimmed" size="sm">
            The page hit an unexpected error. Reloading usually fixes it.
          </Text>
          <Code block>{this.state.error.message}</Code>
          <Button onClick={() => window.location.reload()} w="fit-content">
            Reload
          </Button>
        </Stack>
      </Container>
    );
  }
}
