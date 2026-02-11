package postgres

import (
	"context"
	"database/sql"

	"label-mastering/internal/domain"
)

type JobRepository struct {
	db *sql.DB
}

func NewJobRepository(db *sql.DB) JobRepository {
	return JobRepository{db: db}
}

func (r JobRepository) Save(ctx context.Context, job domain.Job) error {
	_ = ctx
	_ = job
	return nil
}

func (r JobRepository) Update(ctx context.Context, job domain.Job) error {
	_ = ctx
	_ = job
	return nil
}
