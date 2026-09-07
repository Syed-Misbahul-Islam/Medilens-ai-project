console.log("MediLens Backend Starting...");

const express = require("express");
const cors = require("cors");
const helmet = require("helmet");
const morgan = require("morgan");
const rateLimit = require("express-rate-limit");
const fs = require("fs");
const path = require("path");

const env = require("./config/env");

// Routes
const indexRoutes = require("./routes/indexRoutes");
const uploadRoutes = require("./routes/uploadRoutes");
const analyzeRoutes = require("./routes/analyzeRoutes");
const historyRoutes = require("./routes/historyRoutes");
const authRoutes = require("./routes/authRoutes");
const chatRoutes = require("./routes/chatRoutes");
const pdfRoutes = require("./routes/pdfRoutes");
const translateRoutes = require("./routes/translateRoutes");
const doctorRoutes = require("./routes/doctorRoutes");
const videoRoutes = require("./routes/videoRoutes");

const app = express();

// Create uploads folder automatically
const uploadsPath = path.join(__dirname, "uploads");
if (!fs.existsSync(uploadsPath)) {
  fs.mkdirSync(uploadsPath, { recursive: true });
}

// Security & Logging
app.use(helmet());
app.use(morgan("dev"));

// Rate limiting
const limiter = rateLimit({
  windowMs: 15 * 60 * 1000,
  max: 200,
  message: { message: "Too many requests. Please try again later." },
  standardHeaders: true,
  legacyHeaders: false,
});
app.use(limiter);

// CORS & Body Parsing
app.use(cors());
app.use(express.json());

// Health check
app.get("/health", (req, res) => {
  res.json({ status: "ok", timestamp: new Date().toISOString() });
});

// Register routes
app.use("/", indexRoutes);
app.use("/", uploadRoutes);
app.use("/", analyzeRoutes);
app.use("/", historyRoutes);
app.use("/auth", authRoutes);
app.use("/", chatRoutes);
app.use("/", pdfRoutes);
app.use("/", translateRoutes);
app.use("/", doctorRoutes);
app.use("/", videoRoutes);

// Global error handler
app.use((err, req, res, next) => {
  console.error("Unhandled error:", err.message);
  res.status(err.status || 500).json({
    message: err.message || "Internal server error",
  });
});

app.listen(env.port, () => {
  console.log(`Server running on http://localhost:${env.port}`);
});
