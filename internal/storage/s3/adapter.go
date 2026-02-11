package s3

import "context"

type Adapter struct {
	bucket string
}

func NewAdapter(bucket string) Adapter {
	return Adapter{bucket: bucket}
}

func (a Adapter) DownloadToPath(ctx context.Context, objectKey, path string) error {
	_ = ctx
	_ = objectKey
	_ = path
	return nil
}
