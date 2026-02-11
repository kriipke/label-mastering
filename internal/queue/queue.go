package queue

import "context"

type Message struct {
	JobID string
}

type Enqueuer interface {
	Enqueue(ctx context.Context, m Message) error
}

type Dequeuer interface {
	Dequeue(ctx context.Context) (Message, error)
}
