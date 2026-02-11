package main

import (
	"log"
	"net/http"

	apphttp "label-mastering/internal/http"
)

func main() {
	mux := http.NewServeMux()
	apphttp.RegisterRoutes(mux)

	addr := ":8080"
	log.Printf("api listening on %s", addr)
	if err := http.ListenAndServe(addr, apphttp.LoggingMiddleware(mux)); err != nil {
		log.Fatal(err)
	}
}
