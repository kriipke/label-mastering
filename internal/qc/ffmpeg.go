package qc

import (
	"context"
	"errors"
)

type FFmpegOrchestrator struct{}

func NewFFmpegOrchestrator() FFmpegOrchestrator {
	return FFmpegOrchestrator{}
}

func (o FFmpegOrchestrator) Analyze(ctx context.Context, in Input) (Result, error) {
	_ = ctx
	_ = in
	return Result{}, errors.New("ffmpeg orchestration not implemented")
}
