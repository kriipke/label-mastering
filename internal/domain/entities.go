package domain

import "time"

type MixType string

const (
	MixTypeBeatportMaster MixType = "BEATPORT_MASTER"
	MixTypeSpotifyMaster  MixType = "SPOTIFY_MASTER"
	MixTypeVinylPremaster MixType = "VINYL_PREMASTER"
)

type Release struct {
	ID          string
	Catalog     string
	Label       string
	Artist      string
	Title       string
	ReleaseYear int
	Tracks      []Track
	CreatedAt   time.Time
	UpdatedAt   time.Time
}

type Track struct {
	ID        string
	ReleaseID string
	Artist    string
	Title     string
	Mixes     []MixFile
}

type MixFile struct {
	ID        string
	TrackID   string
	MixType   MixType
	ObjectKey string
	CreatedAt time.Time
}

type JobStatus string

const (
	JobStatusQueued    JobStatus = "QUEUED"
	JobStatusRunning   JobStatus = "RUNNING"
	JobStatusCompleted JobStatus = "COMPLETED"
	JobStatusFailed    JobStatus = "FAILED"
)

type Job struct {
	ID         string
	ReleaseID  string
	TrackID    string
	MixFileID  string
	Status     JobStatus
	Error      string
	Result     *QCResult
	QueuedAt   time.Time
	StartedAt  *time.Time
	FinishedAt *time.Time
}

type QCResult struct {
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
