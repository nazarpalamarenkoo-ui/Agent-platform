import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { Button } from "@/components/ui/button"

test("button responds to click", async () => {
  const onClick = vi.fn()
  render(<Button onClick={onClick}>Log in</Button>)

  await userEvent.click(screen.getByRole("button", { name: "Log in" }))

  expect(onClick).toHaveBeenCalledTimes(1)
})