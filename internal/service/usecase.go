package service

import (
	"context"

	"label-mastering/internal/domain"
	"label-mastering/internal/qc"
)

type JobRepository interface {
	Save(ctx context.Context, job domain.Job) error
	Update(ctx context.Context, job domain.Job) error
}

type JobQueue interface {
	Enqueue(ctx context.Context, job domain.Job) error
}

type Storage interface {
	DownloadToPath(ctx context.Context, objectKey, path string) error
}

type QCUseCase struct {
	jobs    JobRepository
	queue   JobQueue
	storage Storage
	qc      qc.Service
}

func NewQCUseCase(jobs JobRepository, queue JobQueue, storage Storage, qcService qc.Service) QCUseCase {
	return QCUseCase{jobs: jobs, queue: queue, storage: storage, qc: qcService}
}
