import express, { Express } from "express";
import { trace } from "@opentelemetry/api";

const PORT: number = parseInt(process.env.EXPRESS_PORT || "8080");
const app: Express = express();

function getRandomNumber(min: number, max: number) {
  return Math.floor(Math.random() * (max - min) + min);
}

app.get("/rolldice", (req, res) => {
  // read the query parameter error
  const error = req.query.error;
  if (error) {
    res.status(500).send("Internal Server Error");
    return;
  }

  const tracer = trace.getTracer("example");

  tracer.startActiveSpan("parent-span", async (span) => {
    await new Promise((resolve) => setTimeout(resolve, 1000));
    tracer.startSpan("child-span").end();
    span.end();
  });

  res.send(getRandomNumber(1, 6).toString());
});

app.listen(PORT, () => {
  console.log(`Listening for requests on http://localhost:${PORT}/rolldice`);
});
