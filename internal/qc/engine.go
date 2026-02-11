package qc

import "context"

type Input struct {
	Path     string
	Filename string
	MixType  string
}

type Result struct {
	SampleRate      int
	BitDepth        int
	Channels        int
	IntegratedLUFS  float64
	TruePeakDBTP    float64
	FilenameValid   bool
	MetadataPresent map[string]bool
	Passed          bool
	Failures        []string
}

type Engine interface {
	Analyze(ctx context.Context, in Input) (Result, error)
}

// Service defines transport-agnostic QC logic that can be reused by HTTP handlers,
// worker processes, and CLI tools.
type Service struct {
	engine Engine
}

func NewService(engine Engine) Service {
	return Service{engine: engine}
}

func (s Service) Run(ctx context.Context, in Input) (Result, error) {
	return s.engine.Analyze(ctx, in)
}
