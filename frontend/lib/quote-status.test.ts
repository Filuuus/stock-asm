import { afterEach, describe, expect, it, vi } from "vitest";
import { whatsappUrl } from "./quote-status";

const device = (userAgent: string, maxTouchPoints = 0) => vi.stubGlobal("navigator", { userAgent, maxTouchPoints });

describe("whatsappUrl", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("opens WhatsApp Web on a computer, where wa.me's start-chat page fails for Business accounts", () => {
    device("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)");
    expect(whatsappUrl("33 1234 5678", "Hola")).toBe("https://web.whatsapp.com/send?phone=523312345678&text=Hola");
    expect(whatsappUrl("", "Hola")).toBe("https://web.whatsapp.com/send?text=Hola");
  });

  it("keeps wa.me on phones and on iPads, which report a Mac user agent", () => {
    device("Mozilla/5.0 (Linux; Android 14) Mobile");
    expect(whatsappUrl("3312345678")).toBe("https://wa.me/523312345678");
    device("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)", 5);
    expect(whatsappUrl("3312345678", "Hola")).toBe("https://wa.me/523312345678?text=Hola");
  });
});
