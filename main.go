package main

import (
	"flag"
	"fmt"
	"log"
	"log/slog"
	"net/url"
	"os"

	"github.com/mark3labs/mcp-go/server"
	"github.com/redpanda-data/agent/internal/repository"
	"github.com/redpanda-data/agent/internal/tools"

	_ "github.com/redpanda-data/connect/v4/public/components/all"
)

func main() {
	// repositoryDir := flag.String("dir", "", "A repository directory")
	baseURLStr := flag.String("base-url", "http://localhost:8080", "The base URL to bind the MCP server to")

	flag.Parse()

	args := flag.Args()
	if len(args) == 0 {
		panic("a directory must be provided")
	}

	// Create MCP server
	s := server.NewMCPServer(
		"Redpanda Runtime",
		"1.0.0",
	)

	repositoryDir := args[0]

	resWrapper := tools.NewResourcesWrapper(slog.Default(), s)

	repoScanner := repository.NewScanner(os.DirFS(repositoryDir))
	repoScanner.OnResourceFile(func(resourceType string, filename string, contents []byte) error {
		switch resourceType {
		case "cache":
			if err := resWrapper.AddCache(contents); err != nil {
				return err
			}
		default:
			return fmt.Errorf("resource type '%v' is not supported yet", resourceType)
		}
		return nil
	})
	if err := repoScanner.Scan("."); err != nil {
		panic(err)
	}

	baseURL, err := url.Parse(*baseURLStr)
	if err != nil {
		panic(err)
	}

	sseServer := server.NewSSEServer(s, server.WithBaseURL(*baseURLStr))
	log.Printf("SSE server listening")
	if err := sseServer.Start(":" + baseURL.Port()); err != nil {
		log.Fatalf("Server error: %v", err)
	}
}
