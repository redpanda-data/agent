package main

import (
	"context"
	"errors"
	"flag"
	"fmt"
	"log"
	"net/url"
	"os"

	"github.com/mark3labs/mcp-go/mcp"
	"github.com/mark3labs/mcp-go/server"
	"github.com/redpanda-data/agent/internal/repository"
)

func main() {
	// repositoryDir := flag.String("dir", "", "A repository directory")
	baseURLStr := flag.String("base-url", "http://localhost:8080", "The base URL to bind the MCP server to")

	flag.Parse()

	args := flag.Args()
	if len(args) == 0 {
		panic("a directory must be provided")
	}

	repositoryDir := args[0]

	// resBuilder := service.NewResourceBuilder()

	repoScanner := repository.NewScanner(os.DirFS(repositoryDir))
	repoScanner.OnResourceFile(func(resourceType string, filename string, contents []byte) error {
		fmt.Println("Meow", resourceType, filename)
		fmt.Println("Woof: ", string(contents))
		return nil
	})
	if err := repoScanner.Scan("."); err != nil {
		panic(err)
	}

	os.Exit(0)

	// Create MCP server
	s := server.NewMCPServer(
		"Redpanda Runtime",
		"1.0.0",
	)

	// Add tool
	tool := mcp.NewTool("hello_world",
		mcp.WithDescription("Say hello to someone"),
		mcp.WithString("name",
			mcp.Required(),
			mcp.Description("Name of the person to greet"),
		),
	)

	baseURL, err := url.Parse(*baseURLStr)
	if err != nil {
		panic(err)
	}

	// Add tool handler
	s.AddTool(tool, helloHandler)

	sseServer := server.NewSSEServer(s, server.WithBaseURL(*baseURLStr))
	log.Printf("SSE server listening")
	if err := sseServer.Start(":" + baseURL.Port()); err != nil {
		log.Fatalf("Server error: %v", err)
	}
}

func helloHandler(ctx context.Context, request mcp.CallToolRequest) (*mcp.CallToolResult, error) {
	name, ok := request.Params.Arguments["name"].(string)
	if !ok {
		return nil, errors.New("name must be a string")
	}

	return mcp.NewToolResultText(fmt.Sprintf("Hello, %s!", name)), nil
}
