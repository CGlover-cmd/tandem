import { describe, expect, it } from "vitest";

import { problemCodes } from "./contract.generated";
import { problems } from "./strings";

describe("the contract with Python", () => {
  it("has words for every problem code Python sends", () => {
    const missing = problemCodes.filter((code) => !Object.prototype.hasOwnProperty.call(problems, code));
    expect(missing).toEqual([]);
  });
});
